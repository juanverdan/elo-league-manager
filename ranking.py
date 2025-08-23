import json
import csv
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- CONSTANTES ---
K_FACTOR_DEFAULT = 32
JOGOS_PROVISIONAIS = 5
K_FACTOR_PROVISIONAL = 60
RATING_INICIAL_ATIVO = 1500
RATING_INICIAL_INATIVO = 1200
FATOR_FORCA_EQUIPE = 4

# --- FUNÇÕES DE LEITURA E ESCRITA DE DADOS ---
def carregar_regras_torneios():
    caminho_arquivo = os.path.join(BASE_DIR, 'torneios.json')
    try:
        with open(caminho_arquivo, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def carregar_ratings():
    caminho_arquivo = os.path.join(BASE_DIR, 'ratings.json')
    try:
        with open(caminho_arquivo, 'r', encoding='utf-8') as f: return json.load(f)
    except FileNotFoundError: return {}

def salvar_ratings(ratings_data):
    caminho_arquivo = os.path.join(BASE_DIR, 'ratings.json')
    with open(caminho_arquivo, 'w', encoding='utf-8') as f: json.dump(ratings_data, f, indent=2, ensure_ascii=False)

def carregar_historico():
    caminho_arquivo = os.path.join(BASE_DIR, 'ranking_history.json')
    try:
        with open(caminho_arquivo, 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return []

def salvar_historico(ratings_antigos):
    caminho_arquivo = os.path.join(BASE_DIR, 'ranking_history.json')
    historico = carregar_historico()
    historico.append({'timestamp': datetime.now().isoformat(), 'ratings': ratings_antigos})
    with open(caminho_arquivo, 'w', encoding='utf-8') as f: json.dump(historico, f, indent=2, ensure_ascii=False)

def logar_partida(j_a, j_b, res_a, torn, placar_a, placar_b, fase):
    caminho_arquivo = os.path.join(BASE_DIR, 'partidas.csv')
    header = not os.path.exists(caminho_arquivo) or os.path.getsize(caminho_arquivo) == 0
    with open(caminho_arquivo, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if header:
            writer.writerow(['jogador_a', 'jogador_b', 'resultado_a', 'torneio', 'placar_a', 'placar_b', 'fase'])
        writer.writerow([j_a, j_b, res_a, torn, placar_a, placar_b, fase])

def contar_partidas_jogadas():
    caminho_arquivo = os.path.join(BASE_DIR, 'partidas.csv')
    contagem = {}
    try:
        with open(caminho_arquivo, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for partida in reader:
                contagem[partida['jogador_a']] = contagem.get(partida['jogador_a'], 0) + 1
                contagem[partida['jogador_b']] = contagem.get(partida['jogador_b'], 0) + 1
    except FileNotFoundError: pass
    return contagem

# --- FUNÇÕES DE LÓGICA DO RANKING ---
def calcular_probabilidade_vitoria(rating_a, rating_b):
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))

def atualizar_ratings(rating_a, rating_b, resultado_a, k_a, k_b, prob_a_vence):
    novo_rating_a = rating_a + k_a * (resultado_a - prob_a_vence)
    novo_rating_b = rating_b + k_b * ((1 - resultado_a) - (1 - prob_a_vence))
    return round(novo_rating_a), round(novo_rating_b)

def registrar_partida(jogador_a, jogador_b, resultado_a, torneio, forca_time_a, forca_time_b, placar_a, placar_b, fase):
    regras_lista = carregar_regras_torneios()
    regras_dos_torneios = {t['nome']: t for t in regras_lista}
    
    ratings = carregar_ratings()
    salvar_historico(ratings)
    if jogador_a not in ratings or jogador_b not in ratings: return
    rating_real_a = ratings[jogador_a]
    rating_real_b = ratings[jogador_b]
    diferenca_forca = forca_time_a - forca_time_b
    ajuste_elo = diferenca_forca * FATOR_FORCA_EQUIPE
    rating_virtual_a = rating_real_a + ajuste_elo
    rating_virtual_b = rating_real_b - ajuste_elo
    contagem_jogos = contar_partidas_jogadas()
    jogos_a = contagem_jogos.get(jogador_a, 0)
    jogos_b = contagem_jogos.get(jogador_b, 0)
    k_base = regras_dos_torneios.get(torneio, {}).get('k_factor', K_FACTOR_DEFAULT)
    k_a = K_FACTOR_PROVISIONAL if jogos_a < JOGOS_PROVISIONAIS else k_base
    k_b = K_FACTOR_PROVISIONAL if jogos_b < JOGOS_PROVISIONAIS else k_base
    prob_a_vence = calcular_probabilidade_vitoria(rating_virtual_a, rating_virtual_b)
    novo_rating_a, novo_rating_b = atualizar_ratings(rating_real_a, rating_real_b, resultado_a, k_a, k_b, prob_a_vence)
    ratings[jogador_a] = novo_rating_a
    ratings[jogador_b] = novo_rating_b
    salvar_ratings(ratings)
    logar_partida(jogador_a, jogador_b, resultado_a, torneio, placar_a, placar_b, fase)

def aplicar_bonus_campeonato(torneio_nome, data_fim, resultados):
    regras_lista = carregar_regras_torneios()
    regras_dos_torneios = {t['nome']: t for t in regras_lista}
    
    ratings = carregar_ratings()
    torneio_regras = regras_dos_torneios.get(torneio_nome)
    if not torneio_regras: 
        print(f"Erro: Regras para o torneio '{torneio_nome}' não encontradas.")
        return
    
    salvar_historico(ratings)
    colocacoes_finais = []

    if torneio_regras.get('tipo') == 'Pontos Corridos':
        for jogador, colocacao in resultados.items():
            if not colocacao or not jogador or jogador == 'N/A': continue
            
            colocacao_formatada = f"{colocacao}º Lugar"
            colocacoes_finais.append((jogador, colocacao_formatada))
            
            posicao = int(colocacao)
            if posicao == 1: ratings[jogador] += torneio_regras.get('bonus_campeao', 0)
            elif posicao == 2: ratings[jogador] += torneio_regras.get('bonus_vice', 0)
            elif posicao == 3: ratings[jogador] += torneio_regras.get('bonus_semi', 0)
            elif posicao == 4: ratings[jogador] += torneio_regras.get('bonus_quarto', 0)

    else: # Mata-Mata
        campeao = resultados.get('mm_campeao')
        vice = resultados.get('mm_vice')
        semifinalistas = resultados.get('mm_semi', [])
        quartas = resultados.get('mm_quartas', [])
        
        if campeao and campeao != "N/A":
            ratings[campeao] += torneio_regras.get('bonus_campeao', 0)
            colocacoes_finais.append((campeao, 'Campeão'))
        if vice and vice != "N/A":
            ratings[vice] += torneio_regras.get('bonus_vice', 0)
            colocacoes_finais.append((vice, 'Vice-Campeão'))
        for jogador in semifinalistas:
            if jogador and jogador != "N/A": 
                ratings[jogador] += torneio_regras.get('bonus_semi', 0)
                colocacoes_finais.append((jogador, 'Semifinalista'))
        for jogador in quartas:
            if jogador and jogador != "N/A": 
                colocacoes_finais.append((jogador, 'Quartas de Final'))
    
    salvar_ratings(ratings)
    
    caminho_arquivo = os.path.join(BASE_DIR, 'resultados_torneios.csv')
    header = not os.path.exists(caminho_arquivo) or os.path.getsize(caminho_arquivo) == 0
    with open(caminho_arquivo, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if header: writer.writerow(['jogador', 'torneio', 'colocacao', 'data'])
        for jogador, colocacao in colocacoes_finais:
            writer.writerow([jogador, torneio_nome, colocacao, data_fim])
    
    print("Resultados do torneio salvos com sucesso!")