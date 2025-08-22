from flask import Flask, render_template, request, redirect, url_for, flash, make_response, session
import functools
import json
import csv
import random
import os
from werkzeug.utils import secure_filename
from collections import defaultdict
from datetime import datetime
from unidecode import unidecode
from weasyprint import HTML
from ranking import (
    registrar_partida, contar_partidas_jogadas, aplicar_bonus_campeonato,
    carregar_ratings, salvar_ratings, carregar_regras_torneios, carregar_historico,
    JOGOS_PROVISIONAIS, RATING_INICIAL_ATIVO, RATING_INICIAL_INATIVO
)

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_pode_ser_qualquer_coisa_aleatoria'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static/uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ADMIN_PASSWORD = '123'

def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if 'logged_in' not in session:
            flash("Você precisa estar logado para acessar esta página.", 'error')
            return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view

def carregar_dados_completos():
    ratings_dict = carregar_ratings()
    historico = carregar_historico()
    posicao_anterior = {}
    if historico:
        ultimo_ranking_salvo = historico[-1]['ratings']
        ranking_antigo_ordenado = sorted(ultimo_ranking_salvo.items(), key=lambda item: item[1], reverse=True)
        for i, (jogador, _) in enumerate(ranking_antigo_ordenado):
            posicao_anterior[jogador] = i + 1
    ranking_atual_ordenado = sorted(ratings_dict.items(), key=lambda item: item[1], reverse=True)
    contagem_jogos = contar_partidas_jogadas()
    forma_recente = defaultdict(list)
    caminho_partidas = os.path.join(BASE_DIR, 'partidas.csv')
    try:
        with open(caminho_partidas, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for partida in reader:
                res_a = float(partida['resultado_a'])
                if res_a == 1: forma_recente[partida['jogador_a']].append('W'); forma_recente[partida['jogador_b']].append('L')
                elif res_a == 0.5: forma_recente[partida['jogador_a']].append('D'); forma_recente[partida['jogador_b']].append('D')
                else: forma_recente[partida['jogador_a']].append('L'); forma_recente[partida['jogador_b']].append('W')
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
        ranking_final.append({
            'nome': jogador, 'pontos': rating_atual,'avatar_filename': avatar_filename,
            'mudanca_pontos': rating_atual - RATING_INICIAL_ATIVO if jogos_do_jogador > 0 else 0,
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
    labels_grafico = []; dados_grafico = []
    for snapshot in historico_rating:
        if nome_do_jogador in snapshot['ratings']:
            timestamp = datetime.fromisoformat(snapshot['timestamp']).strftime('%d/%m %H:%M')
            labels_grafico.append(timestamp)
            dados_grafico.append(snapshot['ratings'][nome_do_jogador])
    ranking_atual, _ = carregar_dados_completos()
    for jogador_data in ranking_atual:
        if jogador_data['nome'] == nome_do_jogador:
            labels_grafico.append("Agora")
            dados_grafico.append(jogador_data['pontos'])
            break
    h2h_stats = defaultdict(lambda: {'V': 0, 'E': 0, 'D': 0})
    all_matches_details = []
    caminho_partidas = os.path.join(BASE_DIR, 'partidas.csv')
    try:
        with open(caminho_partidas, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for partida in reader:
                partida_detalhes = { 'torneio': partida.get('torneio'), 'placar_a': partida.get('placar_a', ''), 'placar_b': partida.get('placar_b', ''), 'fase': partida.get('fase', '') }
                if partida['jogador_a'] == nome_do_jogador:
                    oponente = partida['jogador_b']
                    resultado_jogador = float(partida['resultado_a'])
                    partida_detalhes['oponente'] = oponente; partida_detalhes['resultado'] = resultado_jogador
                    all_matches_details.append(partida_detalhes)
                    if resultado_jogador == 1: h2h_stats[oponente]['V'] += 1
                    elif resultado_jogador == 0.5: h2h_stats[oponente]['E'] += 1
                    else: h2h_stats[oponente]['D'] += 1
                elif partida['jogador_b'] == nome_do_jogador:
                    oponente = partida['jogador_a']
                    resultado_jogador = 1 - float(partida['resultado_a']) if partida['resultado_a'] != '0.5' else 0.5
                    partida_detalhes['oponente'] = oponente; partida_detalhes['resultado'] = resultado_jogador
                    all_matches_details.append(partida_detalhes)
                    if resultado_jogador == 1: h2h_stats[oponente]['V'] += 1
                    elif resultado_jogador == 0.5: h2h_stats[oponente]['E'] += 1
                    else: h2h_stats[oponente]['D'] += 1
    except FileNotFoundError: pass
    nome_sem_acento = unidecode(nome_do_jogador)
    avatar_filename = nome_sem_acento.lower().replace(' ', '_') + '.png'
    return render_template(
        'player.html', jogador_nome=nome_do_jogador, historico=historico_conquistas,
        labels_grafico=labels_grafico, dados_grafico=dados_grafico,
        avatar_filename=avatar_filename, h2h_stats=h2h_stats,
        all_matches_details=all_matches_details, titulos_ganhos=titulos_ganhos
    )

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
        j_a = request.form['jogador_a']; j_b = request.form['jogador_b']; res = request.form['resultado']; torn = request.form['torneio']
        forca_a = int(request.form['forca_time_a']); forca_b = int(request.form['forca_time_b'])
        placar_a = int(request.form['placar_a']); placar_b = int(request.form['placar_b'])
        fase = request.form['fase']
        if j_a != j_b:
            res_map = {'vitoria_a': 1, 'empate': 0.5, 'derrota_a': 0}
            registrar_partida(j_a, j_b, res_map[res], torn, forca_a, forca_b, placar_a, placar_b, fase)
            flash(f"Partida registrada com sucesso!", 'success')
        else:
            flash("Erro: Os jogadores devem ser diferentes.", 'error')
        return redirect(url_for('index'))
    _, jogadores = carregar_dados_completos()
    regras_torneios_lista = carregar_regras_torneios()
    nomes_torneios = [torneio['nome'] for torneio in regras_torneios_lista]
    return render_template('registrar.html', jogadores=jogadores, torneios=nomes_torneios)

@app.route('/admin/torneios', methods=['GET', 'POST'])
@login_required
def gerenciar_torneios():
    regras_atuais = carregar_regras_torneios()
    if request.method == 'POST':
        form_type = request.form.get('form_type')
        if form_type == 'add_torneio':
            tipo_torneio = request.form['tipo']
            novo_torneio = {
                "nome": request.form['nome'], "tipo": tipo_torneio,
                "k_factor": int(request.form['k_factor']), "bonus_campeao": int(request.form['bonus_campeao']),
                "bonus_vice": int(request.form['bonus_vice']), "bonus_semi": int(request.form['bonus_semi']),
                "bonus_quarto": int(request.form.get('bonus_quarto', 0)) if tipo_torneio == 'Pontos Corridos' else 0,
                "trophy_img": "", "participantes": []
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

@app.route('/admin/finalizar', methods=['GET', 'POST'])
@login_required
def finalizar_torneio():
    if request.method == 'POST':
        torneio = request.form['torneio_nome']; data = request.form['data_fim']
        primeiro = request.form.get('primeiro'); segundo = request.form.get('segundo')
        terceiro = request.form.get('terceiro'); quarto = request.form.get('quarto')
        campeao = request.form.get('campeao'); vice = request.form.get('vice')
        semi1 = request.form.get('semi1'); semi2 = request.form.get('semi2')
        aplicar_bonus_campeonato(torneio, data, campeao or primeiro, vice or segundo, semi1, semi2, terceiro, quarto)
        flash(f"Torneio '{torneio}' finalizado e bônus aplicados com sucesso!", 'success')
        return redirect(url_for('index'))
    _, jogadores = carregar_dados_completos()
    regras_torneios_lista = carregar_regras_torneios()
    return render_template('finalizar_torneio.html', jogadores=jogadores, torneios=regras_torneios_lista)
    
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
            chances = []; total_bolinhas = 0
            for i, jogador in enumerate(reversed(participantes)):
                if i < len(distribuicao_bolinhas): bolinhas = distribuicao_bolinhas[i]
                else: bolinhas = 1
                chances.append({'nome': jogador['nome'], 'pontos': jogador['pontos'], 'bolinhas': bolinhas})
                total_bolinhas += bolinhas
            for j in chances:
                if total_bolinhas > 0: j['probabilidade'] = (j['bolinhas'] / total_bolinhas) * 100
                else: j['probabilidade'] = 0
            chances.sort(key=lambda x: x['bolinhas'], reverse=True)
            return render_template('draft.html', todos_jogadores=ranking_completo, chances=chances, total_bolinhas=total_bolinhas)
        elif action == 'realizar_sorteio':
            participantes_confirmados = request.form.getlist('participantes_confirmados')
            participantes_data = [p for p in ranking_completo if p['nome'] in participantes_confirmados]
            participantes_data.sort(key=lambda x: x['pontos'], reverse=True)
            distribuicao_bolinhas = [140, 125, 105, 90, 75, 60, 45, 30, 20, 15, 11, 8, 6, 5]
            pote_virtual = []
            for i, jogador in enumerate(reversed(participantes_data)):
                if i < len(distribuicao_bolinhas): bolinhas = distribuicao_bolinhas[i]
                else: bolinhas = 1
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
        dados_jornal = {
            "edicao": request.form['edicao'], "editorial": request.form['editorial'],
            "data_hoje": datetime.now().strftime('%d.%m.%Y'), "partidas": [],
            "ranking_elo": None, "classificacao_campeonato": None
        }
        for p in partidas_para_jornal:
            partida_id = p['id']
            resultado = float(p['resultado_a'])
            vencedor = p['jogador_a'] if resultado == 1 else p['jogador_b'] if resultado == 0 else "Empate"
            perdedor = p['jogador_b'] if resultado == 1 else p['jogador_a'] if resultado == 0 else ""
            resumo_partida = request.form.get(f"resumo_{partida_id}", "Nenhum resumo fornecido.")
            imagem_path = None
            imagem_arquivo = request.files.get(f'imagem_{partida_id}')
            if imagem_arquivo and imagem_arquivo.filename != '':
                filename = secure_filename(imagem_arquivo.filename)
                caminho_salvo = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                imagem_arquivo.save(caminho_salvo)
                imagem_path = f"file:///{caminho_salvo}"
            dados_jornal["partidas"].append({
                "jogador_a": p['jogador_a'], "jogador_b": p['jogador_b'],
                "torneio": p['torneio'], "vencedor": vencedor, "perdedor": perdedor,
                "resumo": resumo_partida, "imagem_path": imagem_path
            })
        if 'incluir_ranking_elo' in request.form:
            ranking, _ = carregar_dados_completos()
            for jogador in ranking:
                avatar_abs_path = os.path.join(BASE_DIR, 'static/images/avatars', jogador['avatar_filename'])
                jogador['avatar_path'] = f"file:///{avatar_abs_path}"
            dados_jornal['ranking_elo'] = ranking
        if 'incluir_classificacao' in request.form:
            jogadores_classificacao = request.form.getlist('classificacao_jogador')
            pontos_classificacao = request.form.getlist('classificacao_pontos')
            tabela = []
            for i in range(len(jogadores_classificacao)):
                if jogadores_classificacao[i] and pontos_classificacao[i]:
                    nome_sem_acento = unidecode(jogadores_classificacao[i])
                    avatar_filename = nome_sem_acento.lower().replace(' ', '_') + '.png'
                    avatar_abs_path = os.path.join(BASE_DIR, 'static/images/avatars', avatar_filename)
                    tabela.append({
                        'jogador': jogadores_classificacao[i], 'pontos': int(pontos_classificacao[i]),
                        'avatar_path': f"file:///{avatar_abs_path}"
                    })
            tabela.sort(key=lambda x: x['pontos'], reverse=True)
            dados_jornal['classificacao_campeonato'] = {
                "nome": request.form.get('nome_campeonato', 'Classificação'), "tabela": tabela
            }
        
        html_para_pdf = render_template('jornal_pdf_template.html', **dados_jornal)
        pdf = HTML(string=html_para_pdf, base_url=BASE_DIR).write_pdf()
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=jornal_liga_edicao_{dados_jornal["edicao"]}.pdf'
        return response
    return render_template('jornal_editor.html', partidas_recentes=reversed(partidas_para_exibir), todos_jogadores=todos_jogadores_nomes, todos_torneios=todos_torneios)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)