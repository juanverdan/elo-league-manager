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

def logar_partida(j_a, j_b, res_a, torn, time_a, time_b, placar_a, placar_b, fase, penaltis_a, penaltis_b):
    caminho_arquivo = os.path.join(BASE_DIR, 'partidas.csv')
    
    header_fields = ['jogador_a', 'jogador_b', 'time_a', 'time_b', 'resultado_a', 'torneio', 
                     'placar_a', 'placar_b', 'fase', 'penaltis_a', 'penaltis_b']
    
    file_exists = os.path.exists(caminho_arquivo) and os.path.getsize(caminho_arquivo) > 0

    with open(caminho_arquivo, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=header_fields)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            'jogador_a': j_a, 'jogador_b': j_b, 'time_a': time_a, 'time_b': time_b, 
            'resultado_a': res_a, 'torneio': torn, 'placar_a': placar_a, 
            'placar_b': placar_b, 'fase': fase, 'penaltis_a': penaltis_a, 'penaltis_b': penaltis_b
        })

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

def registrar_partida(jogador_a, jogador_b, resultado_a, torneio, time_a, time_b, forca_time_a, forca_time_b, placar_a, placar_b, fase, penaltis_a, penaltis_b):
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
    
    logar_partida(jogador_a, jogador_b, resultado_a, torneio, time_a, time_b, placar_a, placar_b, fase, penaltis_a, penaltis_b)

# <<< INÍCIO DA FUNÇÃO ATUALIZADA >>>
def aplicar_bonus_campeonato(torneio_nome, data_fim, resultados):
    regras_lista = carregar_regras_torneios()
    regras_dos_torneios = {t['nome']: t for t in regras_lista}
    
    ratings = carregar_ratings()
    torneio_regras = regras_dos_torneios.get(torneio_nome)
    
    if not torneio_regras: 
        print(f"Erro: Regras para o torneio '{torneio_nome}' não encontradas.")
        return

    # Pega a nova lista de bônus do JSON
    lista_de_bonus = torneio_regras.get('bonus_por_colocacao')
    
    if not lista_de_bonus:
        print(f"Erro: Lista 'bonus_por_colocacao' não encontrada para o torneio '{torneio_nome}'.")
        return
        
    salvar_historico(ratings)
    
    colocacoes_finais_para_salvar = []

    for jogador, info in resultados.items():
        if not info or not jogador or jogador == 'N/A': continue
        
        colocacao_str = info.get('colocacao') # Ex: '1º', '2º', '11º'
        time_utilizado = info.get('time', 'N/A')

        if not colocacao_str: continue

        # Adiciona à lista para salvar no histórico de resultados
        colocacoes_finais_para_salvar.append((jogador, colocacao_str, time_utilizado))
        
        # --- LÓGICA NOVA PARA APLICAR BÔNUS ---
        try:
            # Limpa a string para ter apenas o número (ex: '1º' -> 1)
            colocacao_num = int(''.join(filter(str.isdigit, colocacao_str)))
            
            # Converte para um índice de lista (1º lugar -> índice 0)
            indice = colocacao_num - 1
            
            # Verifica se a colocação tem um bônus correspondente na lista
            if 0 <= indice < len(lista_de_bonus):
                bonus_a_aplicar = lista_de_bonus[indice]
                
                # Aplica o bônus ao rating do jogador
                ratings[jogador] = ratings.get(jogador, RATING_INICIAL_ATIVO) + bonus_a_aplicar
                print(f"Bônus aplicado: {jogador} (+{bonus_a_aplicar} pontos) pela {colocacao_num}ª posição.")
            else:
                print(f"Aviso: Nenhuma pontuação de bônus definida para a {colocacao_num}ª posição no torneio '{torneio_nome}'.")

        except (ValueError, TypeError):
            print(f"Erro ao processar a colocação '{colocacao_str}' para o jogador {jogador}.")
            continue

    salvar_ratings(ratings)
    
    # --- LÓGICA PARA SALVAR OS RESULTADOS NO ARQUIVO CSV ---
    caminho_arquivo = os.path.join(BASE_DIR, 'resultados_torneios.csv')
    header = ['jogador', 'torneio', 'colocacao', 'data', 'time']
    
    try:
        # Usamos 'a' (append) para adicionar ao arquivo sem ler tudo antes
        with open(caminho_arquivo, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=header)
            # Escreve o header apenas se o arquivo estiver vazio (novo ou zerado)
            if f.tell() == 0:
                writer.writeheader()
            
            for jogador, colocacao, time in colocacoes_finais_para_salvar:
                writer.writerow({
                    'jogador': jogador, 
                    'torneio': torneio_nome, 
                    'colocacao': colocacao, 
                    'data': data_fim, 
                    'time': time
                })
        print("Resultados do torneio salvos com sucesso no CSV!")
    except IOError as e:
        print(f"Erro ao salvar os resultados do torneio no CSV: {e}")
# <<< FIM DA FUNÇÃO ATUALIZADA >>>