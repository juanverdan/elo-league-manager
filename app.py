from flask import Flask, render_template, request, redirect, url_for, flash, make_response
import json
import csv
import random
import os
from werkzeug.utils import secure_filename
from collections import defaultdict
from datetime import datetime
from unidecode import unidecode
from weasyprint import HTML
from ranking import registrar_partida, contar_partidas_jogadas, JOGOS_PROVISIONAIS, RATING_INICIAL_ATIVO, aplicar_bonus_campeonato

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_pode_ser_qualquer_coisa_aleatoria'
UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static/uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- FUNÇÕES DE CARREGAMENTO ---
def carregar_regras_torneios():
    try:
        with open('torneios.json', 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return []

def carregar_historico():
    try:
        with open('ranking_history.json', 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return []

def carregar_dados_completos():
    try:
        with open('ratings.json', 'r', encoding='utf-8') as f: ratings_dict = json.load(f)
    except FileNotFoundError: return [], []
    
    historico = carregar_historico();posicao_anterior = {}
    if historico:
        ultimo_ranking_salvo = historico[-1]['ratings']
        ranking_antigo_ordenado = sorted(ultimo_ranking_salvo.items(), key=lambda item: item[1], reverse=True)
        for i, (jogador, _) in enumerate(ranking_antigo_ordenado):posicao_anterior[jogador] = i + 1
            
    ranking_atual_ordenado = sorted(ratings_dict.items(), key=lambda item: item[1], reverse=True)
    contagem_jogos = contar_partidas_jogadas();forma_recente = defaultdict(list)
    try:
        with open('partidas.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for partida in reader:
                res_a = float(partida['resultado_a'])
                if res_a == 1: forma_recente[partida['jogador_a']].append('W'); forma_recente[partida['jogador_b']].append('L')
                elif res_a == 0.5: forma_recente[partida['jogador_a']].append('D'); forma_recente[partida['jogador_b']].append('D')
                else: forma_recente[partida['jogador_a']].append('L'); forma_recente[partida['jogador_b']].append('W')
    except FileNotFoundError: pass

    ranking_final = []
    for i, (jogador, rating_atual) in enumerate(ranking_atual_ordenado):
        posicao_atual = i + 1; pos_antiga = posicao_anterior.get(jogador, posicao_atual);status = 'same'; diff = 0
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

@app.route('/registrar', methods=['GET', 'POST'])
def registrar_partida_route():
    if request.method == 'POST':
        j_a = request.form['jogador_a']
        j_b = request.form['jogador_b']
        res = request.form['resultado']
        torn = request.form['torneio']
        forca_a = int(request.form['forca_time_a'])
        forca_b = int(request.form['forca_time_b'])

        if j_a != j_b:
            res_map = {'vitoria_a': 1, 'empate': 0.5, 'derrota_a': 0}
            registrar_partida(j_a, j_b, res_map[res], torn, forca_a, forca_b)
            flash(f"Partida registrada com sucesso!", 'success')
        else:
            flash("Erro: Os jogadores devem ser diferentes.", 'error')
        return redirect(url_for('index'))
    
    _, jogadores = carregar_dados_completos()
    regras_torneios = carregar_regras_torneios()
    nomes_torneios = [torneio['nome'] for torneio in regras_torneios]
    return render_template('registrar.html', jogadores=jogadores, torneios=nomes_torneios)

@app.route('/player/<nome_do_jogador>')
def player_profile(nome_do_jogador):
    historico_conquistas = []
    try:
        with open('resultados_torneios.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['jogador'] == nome_do_jogador:
                    historico_conquistas.append(row)
    except FileNotFoundError: pass

    historico_rating = carregar_historico()
    labels_grafico = []; dados_grafico = []
    for snapshot in historico_rating:
        if nome_do_jogador in snapshot['ratings']:
            timestamp = datetime.fromisoformat(snapshot['timestamp']).strftime('%d/%m %H:%M')
            labels_grafico.append(timestamp)
            dados_grafico.append(snapshot['ratings'][nome_do_jogador])
    ratings_atuais = carregar_dados_completos()[0]
    for jogador_data in ratings_atuais:
        if jogador_data['nome'] == nome_do_jogador:
            labels_grafico.append("Agora")
            dados_grafico.append(jogador_data['pontos'])
            break
            
    nome_sem_acento = unidecode(nome_do_jogador)
    avatar_filename = nome_sem_acento.lower().replace(' ', '_') + '.png'

    return render_template(
        'player.html', jogador_nome=nome_do_jogador, historico=historico_conquistas,
        labels_grafico=labels_grafico, dados_grafico=dados_grafico, avatar_filename=avatar_filename
    )

@app.route('/admin/torneios', methods=['GET', 'POST'])
def gerenciar_torneios():
    regras_atuais = carregar_regras_torneios()
    if request.method == 'POST':
        novo_torneio = { "nome": request.form['nome'], "k_factor": int(request.form['k_factor']), "bonus_campeao": int(request.form['bonus_campeao']), "bonus_vice": int(request.form['bonus_vice']), "bonus_semi": int(request.form['bonus_semi']) }
        regras_atuais.append(novo_torneio)
        with open('torneios.json', 'w', encoding='utf-8') as f:
            json.dump(regras_atuais, f, indent=2, ensure_ascii=False)
        flash(f"Torneio '{novo_torneio['nome']}' adicionado com sucesso!", 'success')
        return redirect(url_for('gerenciar_torneios'))
    return render_template('gerenciar_torneios.html', torneios=regras_atuais)

@app.route('/admin/finalizar', methods=['GET', 'POST'])
def finalizar_torneio():
    if request.method == 'POST':
        torneio = request.form['torneio_nome']; data = request.form['data_fim']; campeao = request.form['campeao']; vice = request.form['vice']; semi1 = request.form['semi1']; semi2 = request.form['semi2']
        aplicar_bonus_campeonato(torneio, data, campeao, vice, semi1, semi2)
        flash(f"Torneio '{torneio}' finalizado e bônus aplicados com sucesso!", 'success')
        return redirect(url_for('index'))
    _, jogadores = carregar_dados_completos()
    regras_torneios = carregar_regras_torneios()
    nomes_torneios = [t['nome'] for t in regras_torneios]
    return render_template('finalizar_torneio.html', jogadores=jogadores, torneios=nomes_torneios)

@app.route('/draft', methods=['GET', 'POST'])
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
                if i < len(distribuicao_bolinhas):
                    bolinhas = distribuicao_bolinhas[i]
                else:
                    bolinhas = 1
                chances.append({'nome': jogador['nome'], 'pontos': jogador['pontos'], 'bolinhas': bolinhas})
                total_bolinhas += bolinhas
            for j in chances:
                if total_bolinhas > 0:
                    j['probabilidade'] = (j['bolinhas'] / total_bolinhas) * 100
                else:
                    j['probabilidade'] = 0
            chances.sort(key=lambda x: x['bolinhas'], reverse=True)
            return render_template('draft.html', todos_jogadores=ranking_completo, chances=chances, total_bolinhas=total_bolinhas)
        elif action == 'realizar_sorteio':
            participantes_confirmados = request.form.getlist('participantes_confirmados')
            participantes_data = [p for p in ranking_completo if p['nome'] in participantes_confirmados]
            participantes_data.sort(key=lambda x: x['pontos'], reverse=True)
            distribuicao_bolinhas = [140, 125, 105, 90, 75, 60, 45, 30, 20, 15, 11, 8, 6, 5]
            pote_virtual = []
            for i, jogador in enumerate(reversed(participantes_data)):
                if i < len(distribuicao_bolinhas):
                    bolinhas = distribuicao_bolinhas[i]
                else:
                    bolinhas = 1
                pote_virtual.extend([jogador['nome']] * bolinhas)
            random.shuffle(pote_virtual)
            draft_results = []
            while len(draft_results) < len(participantes_data):
                if not pote_virtual: break
                escolhido = random.choice(pote_virtual)
                if escolhido not in draft_results:
                    draft_results.append(escolhido)
            return render_template('draft.html', draft_results=draft_results)
    return render_template('draft.html', todos_jogadores=ranking_completo)

@app.route('/admin/jornal', methods=['GET', 'POST'])
def jornal_liga():
    partidas_recentes = []
    try:
        with open('partidas.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                row['id'] = i
                partidas_recentes.append(row)
    except FileNotFoundError:
        pass
    
    if request.method == 'POST':
        indices_selecionados = [int(i) for i in request.form.getlist('partidas_selecionadas')]
        
        dados_jornal = {
            "edicao": request.form['edicao'],
            "editorial": request.form['editorial'],
            "data_hoje": datetime.now().strftime('%d.%m.%Y'),
            "partidas": []
        }
        for i in indices_selecionados:
            p = partidas_recentes[i]
            resultado = float(p['resultado_a'])
            vencedor = p['jogador_a'] if resultado == 1 else p['jogador_b'] if resultado == 0 else "Empate"
            perdedor = p['jogador_b'] if resultado == 1 else p['jogador_a'] if resultado == 0 else ""
            resumo_partida = request.form.get(f"resumo_{i}", "Nenhum resumo fornecido.")
            
            imagem_path = None
            imagem_arquivo = request.files.get(f'imagem_{i}')
            if imagem_arquivo and imagem_arquivo.filename != '':
                filename = secure_filename(imagem_arquivo.filename)
                caminho_salvo = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                imagem_arquivo.save(caminho_salvo)
                imagem_path = f"file:///{caminho_salvo}"
            
            dados_jornal["partidas"].append({
                "jogador_a": p['jogador_a'], "jogador_b": p['jogador_b'],
                "torneio": p['torneio'], "vencedor": vencedor, "perdedor": perdedor,
                "resumo": resumo_partida,
                "imagem_path": imagem_path
            })
        
        html_para_pdf = render_template('jornal_pdf_template.html', **dados_jornal)
        pdf = HTML(string=html_para_pdf).write_pdf()
        
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=jornal_liga_edicao_{dados_jornal["edicao"]}.pdf'
        
        return response

    return render_template('jornal_editor.html', partidas_recentes=reversed(partidas_recentes))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)