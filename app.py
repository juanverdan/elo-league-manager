import os
from dotenv import load_dotenv
import functools
import json
import csv
import random
import requests
from werkzeug.utils import secure_filename
from collections import defaultdict
from datetime import datetime, timedelta
from unidecode import unidecode
from weasyprint import HTML

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

from flask import Flask, render_template, request, redirect, url_for, flash, make_response, session
from ranking import (
    registrar_partida, contar_partidas_jogadas, aplicar_bonus_campeonato,
    carregar_ratings, salvar_ratings, carregar_regras_torneios, carregar_historico,
    JOGOS_PROVISIONAIS, RATING_INICIAL_ATIVO, RATING_INICIAL_INATIVO
)

app = Flask(__name__)

# Configurações da aplicação
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'uma_chave_secreta_padrao_se_nao_definida')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')
API_FOOTBALL_KEY = os.getenv('API_FOOTBALL_KEY')

# Configuração de diretórios
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static/uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- DECORATORS E FUNÇÕES AUXILIARES ---

def login_required(view):
    """Decorator que exige login para acessar uma rota."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if 'logged_in' not in session:
            flash("Você precisa estar logado para acessar esta página.", 'error')
            return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view

def carregar_escudos():
    """Carrega os dados de escudos do arquivo JSON."""
    caminho_arquivo = os.path.join(BASE_DIR, 'escudos.json')
    try:
        with open(caminho_arquivo, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def salvar_escudos(escudos_data):
    """Salva os dados de escudos no arquivo JSON."""
    caminho_arquivo = os.path.join(BASE_DIR, 'escudos.json')
    with open(caminho_arquivo, 'w', encoding='utf-8') as f:
        json.dump(escudos_data, f, indent=2, ensure_ascii=False)

def carregar_dados_completos():
    """Carrega e processa todos os dados necessários para o ranking."""
    ratings_dict = carregar_ratings()
    historico = carregar_historico()
    
    posicao_anterior = {}
    rating_anterior = {}
    
    # --- LÓGICA NOVA E DEFINITIVA: VARIAÇÃO DIÁRIA ---
    agora = datetime.now()
    # Pega o início do dia de hoje (meia-noite) como referência
    inicio_do_dia_de_hoje = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    ranking_referencia = None

    if historico:
        # Procura o último registro feito ANTES de hoje começar (ou seja, o rating do final de ontem)
        for snapshot in reversed(historico):
            timestamp_snapshot = datetime.fromisoformat(snapshot['timestamp'])
            if timestamp_snapshot < inicio_do_dia_de_hoje:
                ranking_referencia = snapshot['ratings']
                break

        # Se não houver registros de dias anteriores, usa o mais antigo que tiver
        if not ranking_referencia and historico:
            ranking_referencia = historico[0]['ratings']
    # --- FIM DA LÓGICA NOVA ---
            
    if ranking_referencia:
        # O resto do código preenche os dados com base no ranking de referência encontrado
        ranking_antigo_ordenado = sorted(ranking_referencia.items(), key=lambda item: item[1], reverse=True)
        for i, (jogador, rating) in enumerate(ranking_antigo_ordenado):
            posicao_anterior[jogador] = i + 1
            rating_anterior[jogador] = rating

    ranking_atual_ordenado = sorted(ratings_dict.items(), key=lambda item: item[1], reverse=True)
    contagem_jogos = contar_partidas_jogadas()
    
    forma_recente = defaultdict(list)
    caminho_partidas = os.path.join(BASE_DIR, 'partidas.csv')
    try:
        with open(caminho_partidas, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for partida in reader:
                res_a = float(partida['resultado_a'])
                if res_a == 1:
                    forma_recente[partida['jogador_a']].append('W')
                    forma_recente[partida['jogador_b']].append('L')
                elif res_a == 0.5:
                    forma_recente[partida['jogador_a']].append('D')
                    forma_recente[partida['jogador_b']].append('D')
                else:
                    forma_recente[partida['jogador_a']].append('L')
                    forma_recente[partida['jogador_b']].append('W')
    except FileNotFoundError: pass

    ranking_final = []
    for i, (jogador, rating_atual) in enumerate(ranking_atual_ordenado):
        posicao_atual = i + 1
        pos_antiga = posicao_anterior.get(jogador, posicao_atual)
        status = 'same'; diff = 0
        if pos_antiga > posicao_atual: status = 'up'; diff = pos_antiga - posicao_atual
        elif pos_antiga < posicao_atual: status = 'down'; diff = posicao_atual - pos_antiga
        jogos_do_jogador = contagem_jogos.get(jogador, 0)
        nome_sem_acento = unidecode(jogador)
        avatar_filename = nome_sem_acento.lower().replace(' ', '_') + '.png'
        rating_de_referencia = rating_anterior.get(jogador, rating_atual)
        mudanca_pontos_24h = rating_atual - rating_de_referencia
        
        ranking_final.append({
            'nome': jogador, 'pontos': int(round(rating_atual)),
            'avatar_filename': avatar_filename, 'mudanca_pontos': int(round(mudanca_pontos_24h)),
            'forma': forma_recente[jogador][-5:], 'posicao_atual': posicao_atual,
            'mudanca_posicao': {'status': status, 'diff': diff},
            'provisional': jogos_do_jogador < JOGOS_PROVISIONAIS
        })
        
    jogadores = sorted(ratings_dict.keys())
    return ranking_final, jogadores

# --- ROTAS DA APLICAÇÃO ---

@app.route('/')
def index():
    ranking, _ = carregar_dados_completos()
    return render_template('ranking.html', ranking=ranking)

@app.route('/player/<nome_do_jogador>')
def player_profile(nome_do_jogador):
    escudos = carregar_escudos()
    historico_conquistas = []
    titulos_ganhos = []
    regras_dos_torneios_lista = carregar_regras_torneios()
    regras_dos_torneios_dict = {t['nome']: t for t in regras_dos_torneios_lista}

    caminho_resultados = os.path.join(BASE_DIR, 'resultados_torneios.csv')
    try:
        with open(caminho_resultados, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['jogador'] == nome_do_jogador:
                    historico_conquistas.append(row)
                    if '1º' in row['colocacao'] or 'Campeão' in row['colocacao']:
                        nome_torneio = row['torneio']
                        if nome_torneio in regras_dos_torneios_dict:
                            titulos_ganhos.append({
                                'nome': nome_torneio,
                                'imagem': regras_dos_torneios_dict[nome_torneio].get('trophy_img', 'default_trophy.png')
                            })
    except FileNotFoundError: pass

    historico_rating = carregar_historico()
    daily_ratings = {}
    for snapshot in historico_rating:
        if nome_do_jogador in snapshot['ratings']:
            date_key = datetime.fromisoformat(snapshot['timestamp']).strftime('%Y-%m-%d')
            daily_ratings[date_key] = snapshot['ratings'][nome_do_jogador]
    labels_grafico, dados_grafico = [], []
    for date_key, rating in sorted(daily_ratings.items()):
        formatted_date = datetime.strptime(date_key, '%Y-%m-%d').strftime('%d/%m')
        labels_grafico.append(formatted_date)
        dados_grafico.append(rating)
    ranking_atual, _ = carregar_dados_completos()
    for jogador_data in ranking_atual:
        if jogador_data['nome'] == nome_do_jogador:
            if not labels_grafico or datetime.now().strftime('%d/%m') != labels_grafico[-1]:
                labels_grafico.append("Hoje")
                dados_grafico.append(jogador_data['pontos'])
            break
            
    h2h_stats = defaultdict(lambda: {'V': 0, 'E': 0, 'D': 0})
    all_matches_details = []
    caminho_partidas = os.path.join(BASE_DIR, 'partidas.csv')
    try:
        with open(caminho_partidas, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for partida in reader:
                oponente = None; match_details = {}
                if partida['jogador_a'] == nome_do_jogador:
                    oponente = partida['jogador_b']
                    resultado_para_perfil = float(partida['resultado_a'])
                    match_details = {'jogador_time': partida.get('time_a'), 'oponente_time': partida.get('time_b'), 'jogador_placar': partida.get('placar_a'), 'oponente_placar': partida.get('placar_b'), 'jogador_penaltis': partida.get('penaltis_a'), 'oponente_penaltis': partida.get('penaltis_b')}
                elif partida['jogador_b'] == nome_do_jogador:
                    oponente = partida['jogador_a']
                    resultado_para_perfil = 1.0 - float(partida['resultado_a'])
                    match_details = {'jogador_time': partida.get('time_b'), 'oponente_time': partida.get('time_a'), 'jogador_placar': partida.get('placar_b'), 'oponente_placar': partida.get('placar_a'), 'jogador_penaltis': partida.get('penaltis_b'), 'oponente_penaltis': partida.get('penaltis_a')}
                if oponente:
                    if resultado_para_perfil == 1: h2h_stats[oponente]['V'] += 1
                    elif resultado_para_perfil == 0.5: h2h_stats[oponente]['E'] += 1
                    else: h2h_stats[oponente]['D'] += 1
                    match_details.update({'torneio': partida.get('torneio'), 'fase': partida.get('fase', ''), 'oponente': oponente, 'resultado_final': resultado_para_perfil})
                    all_matches_details.append(match_details)
    except FileNotFoundError: pass
    
    nome_sem_acento = unidecode(nome_do_jogador)
    avatar_filename = nome_sem_acento.lower().replace(' ', '_') + '.png'
    return render_template('player.html', jogador_nome=nome_do_jogador, historico=historico_conquistas, labels_grafico=labels_grafico, dados_grafico=dados_grafico, avatar_filename=avatar_filename, h2h_stats=h2h_stats, all_matches_details=all_matches_details, titulos_ganhos=titulos_ganhos, escudos=escudos)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True
            flash("Login realizado com sucesso!", 'success')
            return redirect(url_for('index'))
        else:
            flash("Senha incorreta.", 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash("Você foi desconectado.", 'success')
    return redirect(url_for('index'))

@app.route('/registrar', methods=['GET', 'POST'])
@login_required
def registrar_partida_route():
    if request.method == 'POST':
        jogadores_a = request.form.getlist('jogador_a')
        jogadores_b = request.form.getlist('jogador_b')
        resultados = request.form.getlist('resultado')
        torneios = request.form.getlist('torneio')
        times_a = request.form.getlist('time_a')
        times_b = request.form.getlist('time_b')
        forcas_a = request.form.getlist('forca_time_a')
        forcas_b = request.form.getlist('forca_time_b')
        placares_a = request.form.getlist('placar_a')
        placares_b = request.form.getlist('placar_b')
        fases = request.form.getlist('fase')
        penaltis_as = request.form.getlist('penaltis_a')
        penaltis_bs = request.form.getlist('penaltis_b')

        partidas_registradas = 0
        for i in range(len(jogadores_a)):
            j_a, j_b = jogadores_a[i], jogadores_b[i]
            if not j_a or not j_b: continue
            if j_a != j_b:
                res_map = {'vitoria_a': 1, 'empate': 0.5, 'derrota_a': 0}
                registrar_partida(
                    j_a, j_b, res_map[resultados[i]], torneios[i],
                    times_a[i], times_b[i], int(forcas_a[i]), int(forcas_b[i]),
                    int(placares_a[i]), int(placares_b[i]), fases[i],
                    penaltis_as[i], penaltis_bs[i]
                )
                partidas_registradas += 1
            else:
                flash(f"Erro na partida {i+1}: Jogadores devem ser diferentes. Partida ignorada.", 'error')
        if partidas_registradas > 0:
            flash(f"{partidas_registradas} partida(s) registrada(s) com sucesso!", 'success')
        return redirect(url_for('index'))
    
    _, jogadores = carregar_dados_completos()
    regras_torneios_lista = carregar_regras_torneios()
    nomes_torneios = [torneio['nome'] for torneio in regras_torneios_lista]
    escudos = carregar_escudos()
    nomes_dos_times = sorted(list(escudos.keys()))
    return render_template('registrar.html', jogadores=jogadores, torneios=nomes_torneios, nomes_dos_times=nomes_dos_times)

# --- ROTAS DE ADMINISTRAÇÃO ---

@app.route('/admin/torneios', methods=['GET', 'POST'])
@login_required
def gerenciar_torneios():
    regras_atuais = carregar_regras_torneios()
    if request.method == 'POST':
        form_type = request.form.get('form_type')
        if form_type == 'add_torneio':
            # Removido bonus_campeao, vice, etc. e adicionado bonus_por_colocacao
            bonus_str = request.form.get('bonus_por_colocacao', '')
            bonus_list = [int(b.strip()) for b in bonus_str.split(',') if b.strip()]
            
            novo_torneio = {
                "nome": request.form['nome'], 
                "tipo": request.form['tipo'],
                "k_factor": int(request.form['k_factor']),
                "bonus_por_colocacao": bonus_list, # Nova estrutura de bônus
                "trophy_img": request.form.get('trophy_img', 'default_trophy.png'),
                "participantes": []
            }
            regras_atuais.append(novo_torneio)
            flash(f"Torneio '{novo_torneio['nome']}' adicionado com sucesso!", 'success')
        elif form_type == 'add_participantes':
            torneio_selecionado = request.form.get('torneio_selecionado')
            participantes_selecionados = request.form.getlist('participantes')
            for torneio in regras_atuais:
                if torneio['nome'] == torneio_selecionado:
                    torneio['participantes'] = participantes_selecionados
                    break
            flash(f"Participantes atualizados para o torneio '{torneio_selecionado}'!", 'success')
        with open(os.path.join(BASE_DIR, 'torneios.json'), 'w', encoding='utf-8') as f:
            json.dump(regras_atuais, f, indent=2, ensure_ascii=False)
        return redirect(url_for('gerenciar_torneios'))
    _, todos_jogadores = carregar_dados_completos()
    return render_template('gerenciar_torneios.html', torneios=regras_atuais, todos_jogadores=todos_jogadores)

@app.route('/admin/escudos', methods=['GET', 'POST'])
@login_required
def gerenciar_escudos():
    escudos = carregar_escudos()
    if request.method == 'POST':
        nome_time_busca, pais = request.form.get('nome_time'), request.form.get('pais')
        if not API_FOOTBALL_KEY or API_FOOTBALL_KEY == "SUA_API_KEY_AQUI":
            flash("Erro: A chave da API de Futebol não está configurada no arquivo .env.", 'error')
            return redirect(url_for('gerenciar_escudos'))
        url, headers = "https://v3.football.api-sports.io/teams", {'x-rapidapi-host': "v3.football.api-sports.io", 'x-apisports-key': API_FOOTBALL_KEY}
        params = {"name": nome_time_busca, "country": pais}
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get('errors') and len(data.get('errors')) > 0:
                flash(f"A API retornou um erro: {str(data['errors'])}", 'error')
            elif data.get('results', 0) > 0 and data.get('response'):
                time_info = data['response'][0]['team']
                nome_oficial, url_escudo = time_info['name'], time_info['logo']
                if time_info.get('national', False): nome_oficial = f"{time_info['name']} (Seleção)"
                escudos[nome_oficial] = url_escudo
                salvar_escudos(escudos)
                flash(f"Escudo para '{nome_oficial}' salvo com sucesso!", 'success')
            else:
                flash(f"Nenhum time encontrado para '{nome_time_busca}' no país '{pais}'.", 'error')
        except requests.exceptions.RequestException as e:
            flash(f"Erro de conexão com a API: {e}", 'error')
        return redirect(url_for('gerenciar_escudos'))
    return render_template('gerenciar_escudos.html', escudos=escudos)

# <<< INÍCIO DA FUNÇÃO ATUALIZADA >>>
@app.route('/admin/finalizar', methods=['GET', 'POST'])
@login_required
def finalizar_torneio():
    regras_torneios_lista = carregar_regras_torneios()
    if request.method == 'POST':
        torneio_nome = request.form.get('torneio_nome')
        data_fim = request.form.get('data_fim')
        
        torneio_selecionado = next((t for t in regras_torneios_lista if t['nome'] == torneio_nome), None)
        
        if not torneio_selecionado:
            flash(f"Erro: Torneio '{torneio_nome}' não encontrado.", 'error')
            return redirect(url_for('finalizar_torneio'))

        resultados = {}
        participantes_do_torneio = torneio_selecionado.get('participantes', [])

        for jogador in participantes_do_torneio:
            colocacao = request.form.get(f'colocacao_{jogador}')
            time = request.form.get(f'time_{jogador}')
            
            if colocacao and time:
                # Armazena a colocação para ser processada pela função de bônus
                resultados[jogador] = {'colocacao': f'{colocacao}º', 'time': time}
        
        # A função aplicar_bonus_campeonato (em ranking.py) deve ser ajustada 
        # para usar a lista 'bonus_por_colocacao' do JSON do torneio.
        aplicar_bonus_campeonato(torneio_nome, data_fim, resultados)
        
        flash(f"Torneio '{torneio_nome}' finalizado e bônus aplicados com sucesso!", 'success')
        return redirect(url_for('index'))
        
    _, jogadores = carregar_dados_completos()
    escudos = carregar_escudos()
    nomes_dos_times = sorted(list(escudos.keys()))
    return render_template('finalizar_torneio.html', jogadores=jogadores, torneios=regras_torneios_lista, nomes_dos_times=nomes_dos_times)
# <<< FIM DA FUNÇÃO ATUALIZADA >>>
    
@app.route('/admin/jogadores', methods=['GET', 'POST'])
@login_required
def gerenciar_jogadores():
    ratings_dict = carregar_ratings()
    if request.method == 'POST':
        novo_jogador = request.form.get('nome_jogador')
        if novo_jogador and novo_jogador.strip():
            nome_jogador_tratado = novo_jogador.strip()
            if nome_jogador_tratado not in ratings_dict:
                ratings_dict[nome_jogador_tratado] = RATING_INICIAL_INATIVO
                salvar_ratings(ratings_dict)
                flash(f"Jogador '{nome_jogador_tratado}' adicionado com {RATING_INICIAL_INATIVO} pontos!", 'success')
            else:
                flash(f"Erro: Jogador '{nome_jogador_tratado}' já existe.", 'error')
        else:
            flash("Erro: Nome do jogador não pode ser vazio.", 'error')
        return redirect(url_for('gerenciar_jogadores'))
    jogadores_ordenados = sorted(ratings_dict.items())
    return render_template('gerenciar_jogadores.html', jogadores=jogadores_ordenados)

@app.route('/draft', methods=['GET', 'POST'])
@login_required
def draft_lottery():
    ranking_completo, _ = carregar_dados_completos()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'calcular_chances':
            participantes_nomes = request.form.getlist('participantes')
            participantes = [p for p in ranking_completo if p['nome'] in participantes_nomes]
            participantes.sort(key=lambda x: x['pontos'], reverse=True)
            distribuicao_bolinhas = [140, 125, 105, 90, 75, 60, 45, 30, 20, 15, 11, 8, 6, 5]
            chances, total_bolinhas = [], 0
            for i, jogador in enumerate(reversed(participantes)):
                bolinhas = distribuicao_bolinhas[i] if i < len(distribuicao_bolinhas) else 1
                chances.append({'nome': jogador['nome'], 'pontos': jogador['pontos'], 'bolinhas': bolinhas})
                total_bolinhas += bolinhas
            for j in chances: j['probabilidade'] = (j['bolinhas'] / total_bolinhas) * 100 if total_bolinhas > 0 else 0
            chances.sort(key=lambda x: x['bolinhas'], reverse=True)
            return render_template('draft.html', todos_jogadores=ranking_completo, chances=chances, total_bolinhas=total_bolinhas)
        elif action == 'realizar_sorteio':
            participantes_confirmados = request.form.getlist('participantes_confirmados')
            participantes_data = [p for p in ranking_completo if p['nome'] in participantes_confirmados]
            participantes_data.sort(key=lambda x: x['pontos'], reverse=True)
            distribuicao_bolinhas = [140, 125, 105, 90, 75, 60, 45, 30, 20, 15, 11, 8, 6, 5]
            pote_virtual = []
            for i, jogador in enumerate(reversed(participantes_data)):
                bolinhas = distribuicao_bolinhas[i] if i < len(distribuicao_bolinhas) else 1
                pote_virtual.extend([jogador['nome']] * bolinhas)
            random.shuffle(pote_virtual)
            draft_results = []
            while len(draft_results) < len(participantes_data):
                if not pote_virtual: break
                escolhido = random.choice(pote_virtual)
                if escolhido not in draft_results: draft_results.append(escolhido)
            return render_template('draft.html', draft_results=draft_results)
    return render_template('draft.html', todos_jogadores=ranking_completo)

@app.route('/admin/jornal', methods=['GET', 'POST'])
@login_required
def jornal_liga():
    _, todos_jogadores_nomes = carregar_dados_completos()
    todos_torneios = carregar_regras_torneios()
    todas_as_partidas = []
    caminho_partidas = os.path.join(BASE_DIR, 'partidas.csv')
    try:
        with open(caminho_partidas, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                row['id'] = i
                todas_as_partidas.append(row)
    except FileNotFoundError: pass
    partidas_para_exibir = todas_as_partidas[-10:]
    if request.method == 'POST':
        indices_selecionados = [int(i) for i in request.form.getlist('partidas_selecionadas')]
        partidas_para_jornal = [todas_as_partidas[i] for i in indices_selecionados]
        dados_jornal = {"edicao": request.form['edicao'], "editorial": request.form['editorial'], "data_hoje": datetime.now().strftime('%d.%m.%Y'), "partidas": [], "ranking_elo": None, "classificacao_campeonato": None}
        for p in partidas_para_jornal:
            partida_id, resultado = p['id'], float(p['resultado_a'])
            vencedor = p['jogador_a'] if resultado == 1 else p['jogador_b'] if resultado == 0 else "Empate"
            perdedor = p['jogador_b'] if resultado == 1 else p['jogador_a'] if resultado == 0 else ""
            resumo_partida = request.form.get(f"resumo_{partida_id}", "Nenhum resumo fornecido.")
            imagem_path, imagem_arquivo = None, request.files.get(f'imagem_{partida_id}')
            if imagem_arquivo and imagem_arquivo.filename != '':
                filename = secure_filename(imagem_arquivo.filename)
                caminho_salvo = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                imagem_arquivo.save(caminho_salvo)
                imagem_path = f"file:///{caminho_salvo}"
            dados_jornal["partidas"].append({"jogador_a": p['jogador_a'], "jogador_b": p['jogador_b'], "torneio": p['torneio'], "vencedor": vencedor, "perdedor": perdedor, "resumo": resumo_partida, "imagem_path": imagem_path})
        if 'incluir_ranking_elo' in request.form:
            ranking, _ = carregar_dados_completos()
            for jogador in ranking:
                avatar_abs_path = os.path.join(BASE_DIR, 'static/images/avatars', jogador['avatar_filename'])
                jogador['avatar_path'] = f"file:///{avatar_abs_path}"
            dados_jornal['ranking_elo'] = ranking
        if 'incluir_classificacao' in request.form:
            jogadores_classificacao, pontos_classificacao, posicoes_classificacao = request.form.getlist('classificacao_jogador'), request.form.getlist('classificacao_pontos'), request.form.getlist('classificacao_posicao')
            tabela = []
            for i in range(len(jogadores_classificacao)):
                if jogadores_classificacao[i] and pontos_classificacao[i] and posicoes_classificacao[i]:
                    nome_sem_acento = unidecode(jogadores_classificacao[i])
                    avatar_filename = nome_sem_acento.lower().replace(' ', '_') + '.png'
                    avatar_abs_path = os.path.join(BASE_DIR, 'static/images/avatars', avatar_filename)
                    tabela.append({'jogador': jogadores_classificacao[i], 'pontos': int(pontos_classificacao[i]), 'posicao': int(posicoes_classificacao[i]), 'avatar_path': f"file:///{avatar_abs_path}"})
            tabela.sort(key=lambda x: x['posicao'])
            dados_jornal['classificacao_campeonato'] = {"nome": request.form.get('nome_campeonato', 'Classificação'), "tabela": tabela}
        html_para_pdf = render_template('jornal_pdf_template.html', **dados_jornal)
        pdf = HTML(string=html_para_pdf, base_url=BASE_DIR).write_pdf()
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=jornal_liga_edicao_{dados_jornal["edicao"]}.pdf'
        return response
    return render_template('jornal_editor.html', partidas_recentes=reversed(partidas_para_exibir), todos_jogadores=todos_jogadores_nomes, todos_torneios=todos_torneios)

# --- EXECUÇÃO DA APLICAÇÃO ---

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)