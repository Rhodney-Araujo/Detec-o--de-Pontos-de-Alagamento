import tkinter
import serial
import serial.tools.list_ports
import time
from datetime import datetime, timedelta
from supabase import create_client, Client


url = 'https://dxruudjipgsrkqdycttc.supabase.co'
key = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImR4cnV1ZGppcGdzcmtxZHljdHRjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MjAyODE0NzcsImV4cCI6MjAzNTg1NzQ3N30.wtyKGyfBOKKDuKs63cLkPnwMHn4vw1NCELNUMVFeYTg'

# Conexão com o Supabase
supabase: Client = create_client(url, key)

# Configuração da conexão com o Arduino
def find_arduino():
    ports = list(serial.tools.list_ports.comports())
    for port in ports:
        if 'Arduino' in port.description or 'CH340' in port.description:  # "CH340" é comum em Arduinos clones
            return port.device
    return None

arduino_port = find_arduino()

if arduino_port:
    arduino = serial.Serial(
        port=arduino_port,
        baudrate=9600,
        timeout=1  # Adicione um timeout para evitar travamento em leituras
    )
    print(f"Conectado ao Arduino na porta {arduino_port}")


# Variável para armazenar o ID do último registro inserido
ultimo_id_inserido = None


def inserir_dados(supabase, alagamento_persistente="Sim"):
    global ultimo_id_inserido
    global hora_inicial
    data_hora_atual = datetime.now().strftime('%Y-%m-%d')
    hora_inicial = datetime.now()
    dados = {
        'Alerta': 1,
        'DataHora': data_hora_atual,
        'Endereco': 'Avenida Marginal Pinheiros',
        'AlagamentoPersistente': alagamento_persistente,
        'HoraInicial': hora_inicial.strftime('%H:%M:%S')
    }
    response = supabase.table('sensor').insert(dados).execute()
    if response.data:
        ultimo_id_inserido = response.data[0]['Código']
        print(f"Valor do sensor: 1, Data e Hora: {data_hora_atual}, ID inserido: {ultimo_id_inserido}")
    else:
        print("Erro ao inserir dados no banco.")


def notificacao(supabase):
    titulo = "ALERTA"
    mensagem = "Existe um princípio de alagamento na Av. Marginal Pinheiros"
    dados = {
        'title': titulo,
        'content': mensagem
    }
    supabase.table('Notifications').insert(dados).execute()


def dados_persistentes_true(supabase):
    global ultimo_id_inserido
    if ultimo_id_inserido is not None:
        dados = {
            'AlagamentoPersistente': "Sim",
        }
        supabase.table('sensor').update(dados).eq('Código', ultimo_id_inserido).execute()
        print(f"Alagamento persistente atualizado para sim no registro" , {ultimo_id_inserido} )
    else:
        print("Nenhum ID de registro para atualizar.")


def dados_persistentes_false(supabase):
    global ultimo_id_inserido
    if ultimo_id_inserido is not None:
        hora_final = datetime.now()
        duracao = hora_final - hora_inicial
        duracao_formatada = str(duracao).split('.')[0]  # Remove milissegundos
        dados = {
            'AlagamentoPersistente': "Não",
            'HoraFinal': hora_final.strftime('%H:%M:%S'),  # Converter datetime para string
            'Duração' : duracao_formatada
        }
        supabase.table('sensor').update(dados).eq('Código', ultimo_id_inserido).execute()
        print(f"Alagamento persistente atualizado para não no registro", {ultimo_id_inserido} )
        ultimo_id_inserido = None
    else:
        print("Nenhum ID de registro para atualizar.")


def verif_sinal(sinal):
    if sinal == 1:
        valores_sensor.append(1)
    else:
        valores_sensor.append(0)
    print(f"Lista atualizada: {valores_sensor}")


valores_sensor = []
positividade = False #define que a maioria dos valores foram positvos na lista
em_pausa = False

while True:
    if arduino.inWaiting() > 0:
        message = arduino.readline().decode().strip()
        print("Mensagem recebida:", message)
        sinal = int(message)
        verif_sinal(sinal)

        # Verificação inicial com 55 leituras
        if len(valores_sensor) == 55: #55 verificações
            positivos = valores_sensor.count(1)
            negativos = valores_sensor.count(0)

            if positivos > negativos:
                inserir_dados(supabase)
                positividade = True
                print("Maioria positiva nas primeiras 55 leituras. Inserindo no banco e aguardando 10 minutos.")
                valores_sensor = []
                arduino.close()
                time.sleep(600) #10 minutos
                arduino = serial.Serial(port = arduino_port, baudrate = 9600)

            else:
                print("Maioria negativa nas primeiras 55 leituras. Reiniciando...")
                valores_sensor = []
                arduino.close()
                time.sleep(600) #10 minutos
                arduino = serial.Serial(port = arduino_port, baudrate = 9600)

        # Após a pausa, fazer 51 leituras e continuar o fluxo
        if positividade and len(valores_sensor) >= 51:
            positivos = valores_sensor.count(1)
            negativos = valores_sensor.count(0)

            if positivos > negativos:
                dados_persistentes_true(supabase)
                notificacao(supabase)
                print("Maioria positiva nas 51 leituras. Alagamento persistente.")
            else:
                dados_persistentes_false(supabase)
                print("Maioria negativa nas 51 leituras. Marcando como alagamento não persistente.")
                positividade = False  # Resetar para começar uma nova rodada

            valores_sensor = []
            arduino.close()
            time.sleep(600) # Esperar 10 minutos antes de começar uma nova rodada de 55 leituras
            arduino = serial.Serial(port = arduino_port, baudrate = 9600)


    time.sleep(2)
