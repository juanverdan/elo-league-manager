import json

dados_historicos = [
    {'jogador': 'André', 'Champions C1': 1000, 'Série B': 1000, 'CdB B': 45, 'UNICEF Cup': 500},
    {'jogador': 'Valdo', 'Champions C1': None, 'Série B': 750, 'CdB B': 300, 'UNICEF Cup': 300},
    {'jogador': 'Hericles', 'Champions C1': 180, 'Série B': 450, 'CdB B': 500, 'UNICEF Cup': 180},
    {'jogador': 'Ramon', 'Champions C1': 180, 'Série B': 600, 'CdB B': 180, 'UNICEF Cup': 45},
    {'jogador': 'Daniel Campos', 'Champions C1': 360, 'Série B': 400, 'CdB B': 90, 'UNICEF Cup': 45},
    {'jogador': 'Indiano', 'Champions C1': 360, 'Série B': 250, 'CdB B': 10, 'UNICEF Cup': 90},
    {'jogador': 'Davi', 'Champions C1': 10, 'Série B': 500, 'CdB B': 45, 'UNICEF Cup': 90},
    {'jogador': 'Tiago', 'Champions C1': 90, 'Série B': 180, 'CdB B': 180, 'UNICEF Cup': 180},
    {'jogador': 'Samuel', 'Champions C1': 180, 'Série B': 300, 'CdB B': 45, 'UNICEF Cup': 90},
    {'jogador': 'Lavieri', 'Champions C1': 90, 'Série B': 350, 'CdB B': 45, 'UNICEF Cup': 45},
    {'jogador': 'Emanuel', 'Champions C1': 90, 'Série B': 200, 'CdB B': 90, 'UNICEF Cup': None},
    {'jogador': 'Temis', 'Champions C1': 180, 'Série B': None, 'CdB B': None, 'UNICEF Cup': 10},
    {'jogador': 'Wesley', 'Champions C1': 90, 'Série B': None, 'CdB B': None, 'UNICEF Cup': 90},
    {'jogador': 'João Carlos', 'Champions C1': None, 'Série B': 160, 'CdB B': 10, 'UNICEF Cup': None},
    {'jogador': 'Ledin', 'Champions C1': 90, 'Série B': None, 'CdB B': None, 'UNICEF Cup': 45},
    {'jogador': 'Alex Markes', 'Champions C1': 90, 'Série B': None, 'CdB B': None, 'UNICEF Cup': 45},
    {'jogador': 'Laura', 'Champions C1': None, 'Série B': None, 'CdB B': None, 'UNICEF Cup': None},
]

# --- CONFIGURAÇÕES DA SIMULAÇÃO ---
PESOS_TORNEIO = {'Champions C1': 1000, 'Série B': 1000, 'CdB B': 500, 'UNICEF Cup': 500}
FATOR_DE_ESCALA = 0.25 # Manter o fator alto para um ranking bem distribuído

# --- NOVAS CONSTANTES ---
RATING_INICIAL_ATIVO = 1500
RATING_INICIAL_INATIVO = 1200 # O rating para jogadores que nunca participaram

def simular():
    ratings = {}
    # Itera sobre os jogadores para definir o rating inicial correto
    for jogador_data in dados_historicos:
        nome = jogador_data['jogador']
        # Verifica se o jogador tem alguma pontuação em qualquer torneio
        participou = any(v is not None for k, v in jogador_data.items() if k != 'jogador')
        if participou:
            ratings[nome] = RATING_INICIAL_ATIVO
        else:
            ratings[nome] = RATING_INICIAL_INATIVO
            print(f"Jogador inativo detectado: {nome}. Definindo rating inicial para {RATING_INICIAL_INATIVO}.")

    print("\n--- INICIANDO SIMULAÇÃO HISTÓRICA ---")

    ordem_torneios = ['Champions C1', 'Série B', 'CdB B', 'UNICEF Cup']

    for torneio in ordem_torneios:
        print(f"--- Simulando Torneio: {torneio} ---")
        participantes = []
        pontos_total = 0
        for jogador_data in dados_historicos:
            pontos = jogador_data.get(torneio)
            if pontos is not None:
                participantes.append({'nome': jogador_data['jogador'], 'pontos': pontos})
                pontos_total += pontos
        if not participantes: continue
        media_pontos = pontos_total / len(participantes)
        print(f"Participantes: {len(participantes)}, Média de pontos no torneio: {media_pontos:.2f}")
        mudancas_elo = {}
        for p in participantes:
            jogador = p['nome']
            pontos_jogador = p['pontos']
            diferenca_de_performance = pontos_jogador - media_pontos
            peso_torneio_normalizado = PESOS_TORNEIO[torneio] / 1000.0
            mudanca = diferenca_de_performance * FATOR_DE_ESCALA * peso_torneio_normalizado
            mudancas_elo[jogador] = round(mudanca)
        for jogador, mudanca in mudancas_elo.items():
            rating_antigo = ratings[jogador]
            ratings[jogador] += mudanca
            print(f"  - {jogador}: {rating_antigo} -> {ratings[jogador]} ({mudanca:+})")
        print("\n")
    print("--- SIMULAÇÃO CONCLUÍDA ---")
    ranking_final_ordenado = sorted(ratings.items(), key=lambda item: item[1], reverse=True)
    for jogador, rating in ranking_final_ordenado:
        print(f"{jogador}: {rating} pontos")
    with open('ratings.json', 'w', encoding='utf-8') as f:
        json.dump(ratings, f, indent=2, ensure_ascii=False)
    print("\nArquivo 'ratings.json' foi atualizado com sucesso!")

if __name__ == "__main__":
    simular()