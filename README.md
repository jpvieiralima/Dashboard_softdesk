# Dashboard — Guia de Instalação

## Arquivos do Projeto

```
dashboard/
├── config.json      ← Configure suas credenciais aqui
├── servidor.py      ← Servidor Python (backend)
├── dashboard.html   ← Dashboard (frontend)
└── README.md        ← Este arquivo
```

## Pré-requisitos

- **Python 3.6+** instalado na máquina (já vem no Windows 10/11 ou instale de python.org)
- Acesso à rede onde o Softdesk está hospedado

## Instalação (5 minutos)

### 1. Copie a pasta para a máquina das TVs

Copie toda a pasta `dashboard` para a máquina que será ligada nas televisões.

### 2. Configure o acesso ao Softdesk

Abra o arquivo `config.json` com qualquer editor de texto e preencha:

```json
{
    "softdesk_url": "https://suaempresa.softdesk.com.br",
    "hash_api": "seu-token-aqui",
    "porta_servidor": 5000,
    "intervalo_atualizacao_segundos": 120
}
```

**Onde encontrar o token (hash_api):**
1. Acesse o Softdesk como administrador
2. Vá em **Administração > Configurações Gerais > Painel de Controle > API**
3. Copie o valor do campo de token/hash

### 3. Inicie o servidor

Abra o terminal/prompt de comando na pasta do projeto e execute:

```bash
python servidor.py
```

Você verá:
```
============================================================
  Dashboard — Servidor Iniciado!
============================================================
  Dashboard: http://localhost:5000
  Suporte:   http://localhost:5000/dashboard.html?view=suporte
  Serviços:  http://localhost:5000/dashboard.html?view=servicos
============================================================
```

### 4. Abra o dashboard no navegador

- **TV 1 (Suporte):** `http://localhost:5000/dashboard.html?view=suporte`
- **TV 2 (Serviços):** `http://localhost:5000/dashboard.html?view=servicos`

Pressione **F11** para tela cheia.

## Acesso de outras máquinas na rede

Substitua `localhost` pelo IP da máquina do servidor:
- Descubra o IP: `ipconfig` (Windows) ou `hostname -I` (Linux)
- Acesse: `http://IP-DA-MAQUINA:5000/dashboard.html?view=suporte`

## Iniciar automaticamente com o Windows

1. Crie um arquivo `iniciar-dashboard.bat` com:
```bat
@echo off
cd /d "%~dp0"
start python servidor.py
timeout /t 5
start chrome --kiosk "http://localhost:5000/dashboard.html?view=suporte"
start chrome --kiosk "http://localhost:5000/dashboard.html?view=servicos"
```
2. Coloque o atalho desse `.bat` em `shell:startup`

## Solução de Problemas

| Problema | Solução |
|----------|---------|
| "Token inválido" | Verifique o hash_api no config.json |
| Dashboard vazio | Aguarde 2 minutos para a primeira coleta |
| Erro de conexão | Verifique se a URL do Softdesk está correta |
| Porta ocupada | Mude a porta no config.json |
