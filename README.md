# Sales Assistant Template

Template de assistente de vendas para WhatsApp focada em captura e qualificação de leads.

## Objetivo

Conduzir uma conversa fluida, simples e comercialmente útil para:
- capturar o lead
- entender necessidade, especificação, orçamento e prazo
- responder dúvidas com segurança
- evitar gasto desnecessário de tokens
- persistir apenas o resultado final e os principais dados no SQLite

## Como rodar

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Para o agente responder no WhatsApp, configure `WAHA_BASE_URL` e `WAHA_API_KEY` no `.env` (usados para chamar `/api/sendText` e baixar mídia).
Você também pode configurar o idioma por DDI com `COUNTRY_LANGUAGE_MAP` (ex.: `55:pt,595:es`).
O webhook exige o header `x-webhook-secret` com o valor de `WAHA_WEBHOOK_SECRET`.
Se o seu WAHA não suporta headers, defina `ALLOW_WEBHOOK_QUERY_SECRET=true` e use o segredo na query string.
Para desativar a autenticação do webhook, use `ALLOW_UNAUTHENTICATED_WEBHOOK=true` (não recomendado em produção).

## Personalização rápida

1. Atualize `APP_NAME`, `BRAND_NAME` e `FAQ_URL` no `.env`.
2. Edite os arquivos em `memory/` para o tom e conteúdo do seu negócio.
3. Ajuste os campos do lead e regras em `app/models/lead.py` e `app/services/lead_service.py` conforme o seu segmento.
4. Se quiser trocar o provedor de comunicação, defina `COMMUNICATION_PROVIDER` (`waha`, `console` ou `http`) e implemente um novo serviço em `app/services/communication_factory.py`.

## Guia de configuração

Veja `docs/configuration_guide.md` para instruções por cenário (WAHA no Docker, app no host, provider HTTP, webhook genérico, etc).

## LLM local (LM Studio / Llama 3)

Você pode apontar o agente para um servidor LM Studio usando o provider `lmstudio`.
Veja o passo a passo em `docs/configuration_guide.md`.

## Arquitetura resumida

1. **WAHA** envia webhook com mensagem de texto ou áudio.
2. **FastAPI** recebe e valida o payload.
3. O sistema verifica **Redis** para sessão, cache de contexto e deduplicação.
4. Se necessário, consulta **SQLite** para histórico mínimo do lead.
5. Se for áudio, transcreve com **faster-whisper**.
6. A entrada consolidada é enviada ao **Agno**, usando **Gemini** como modelo.
7. O agente lê:
   - `memory/agent_profile.md`
   - `memory/agent_guidelines.md`
   - `memory/questionario.md`
   - `memory/agent_aprendizado.md`
8. O agente responde e atualiza apenas o necessário em sessão/cache.
9. Quando a conversa for marcada como concluída, salva os dados principais no **SQLite**.
10. Quando o agente não tiver segurança, aponta para `faq.html` ou transfere para humano.

## Decisões importantes

### 1) Agno como camada de orquestração
Use o Agno para montar o agente e o Gemini como LLM por trás. Isso reduz acoplamento e facilita trocar modelo depois.

### 2) Redis antes de LLM
Antes de consumir tokens:
- verificar se a mensagem é duplicada
- recuperar sessão curta
- recuperar resumo da conversa já existente
- verificar se os dados principais do lead já existem

### 3) SQLite apenas no fechamento
Persistência final apenas quando a conversa for considerada concluída, evitando gravar lixo parcial.

### 4) Aprendizado controlado
`agent_aprendizado.md` não deve receber escrita livre a cada interação. O ideal é registrar apenas padrões aprovados, revisados ou sintetizados por rotina separada para evitar degradar o comportamento do agente.

## Fluxo sugerido da jornada

### Entrada
- Receber `message_id`, `chat_id`, `cellnumber`, `timestamp`, `type`, `text/audio_url`
- Validar assinatura/origem do WAHA
- Deduplicar por `message_id`

### Identificação do contato
- Buscar sessão no Redis por `chat_id` e `cellnumber`
- Se não encontrar ou se a sessão estiver expirada, consultar SQLite
- Se houver lead anterior, usar isso para evitar perguntar novamente o que já é conhecido

### Tratamento do conteúdo
- Texto: seguir direto
- Áudio: baixar mídia, transcrever com faster-whisper, anexar transcrição ao contexto

### Orquestração do agente
- Montar contexto com:
  - perfil
  - diretrizes
  - questionário
  - dados já conhecidos do lead
  - resumo da conversa atual
- O agente deve perguntar **uma pergunta por vez**, com linguagem curta, natural e comercial

### Finalização
- Detectar término por regra de negócio, por exemplo:
  - nome
  - celular
  - especificação desejada
  - preferência/queixa principal
  - faixa de orçamento
  - cidade ou loja de interesse
  - aceitou atendimento humano / proposta
- Salvar no SQLite somente nesse momento

## Estrutura

```text
sales_assistant_agent/
├── app/
│   ├── api/
│   │   └── webhook.py
│   ├── core/
│   │   ├── config.py
│   │   ├── logging.py
│   │   └── prompts.py
│   ├── models/
│   │   └── lead.py
│   ├── repositories/
│   │   ├── lead_repository.py
│   ├── schemas/
│   │   └── webhook.py
│   ├── services/
│   │   ├── agent_service.py
│   │   ├── audio_service.py
│   │   ├── lead_service.py
│   │   ├── redis_service.py
│   │   ├── session_service.py
│   │   └── waha_service.py
│   ├── utils/
│   │   └── text.py
│   └── main.py
├── docs/
│   └── implementation_prompt.md
├── memory/
│   ├── agent_profile.md
│   ├── agent_guidelines.md
│   ├── agent_aprendizado.md
│   └── questionario.md
├── tests/
├── .env.example
├── pyproject.toml
└── README.md
```

## Próximos passos recomendados

1. ligar o payload real do WAHA ao schema
2. definir o critério exato de “conversa finalizada”
3. mapear os campos mínimos do lead para o seu negócio
4. adicionar testes de jornada
5. colocar fila assíncrona para áudio se o volume crescer

## Observações de boas práticas

- Não gravar segredo em código.
- Não confiar cegamente em markdown de memória para decisões críticas.
- Usar timeout e retry com backoff para Gemini e WAHA.
- Tratar idempotência no webhook.
- Sanitizar texto transcrito antes de montar prompt.
- Logar eventos técnicos sem expor conteúdo sensível completo.

## Exemplo de payload do webhook

O webhook aceita o segredo via header `x-webhook-secret` ou via query string `?secret=...`.
O WAHA envia um envelope de evento com `event="message"` e a mensagem em `payload`.

```json
{
  "id": "evt_01aaaaaaaaaaaaaaaaaaaaaaaa",
  "timestamp": 1710960000000,
  "session": "default",
  "engine": "GOWS",
  "event": "message",
  "payload": {
    "id": "false_551199999999@c.us_AAAAAAAAAAAAAAAAAAAA",
    "timestamp": 1710960000,
    "from": "551199999999@c.us",
    "fromMe": false,
    "source": "app",
    "to": "551188888888@c.us",
    "body": "Oi, meu nome é Ana e quero um produto premium.",
    "hasMedia": false
  }
}
```

```json
{
  "id": "evt_01bbbbbbbbbbbbbbbbbbbbbbbb",
  "timestamp": 1710960100000,
  "session": "default",
  "engine": "GOWS",
  "event": "message",
  "payload": {
    "id": "false_551199999999@c.us_BBBBBBBBBBBBBBBBBBBB",
    "timestamp": 1710960100,
    "from": "551199999999@c.us",
    "fromMe": false,
    "source": "app",
    "to": "551188888888@c.us",
    "body": "",
    "hasMedia": true,
    "media": {
      "url": "http://localhost:3000/api/files/false_551199999999@c.us_BBBBBBBBBBBBBBBBBBBB.ogg",
      "mimetype": "audio/ogg"
    }
  }
}
```
1) FastAPI rodando no host (fora do Docker)
Use no WAHA:

http://host.docker.internal:8000/webhook/waha

headers
x-webhook-secret: seu-segredo
## Webhook genérico (entrada)

Além do endpoint do WAHA, você pode enviar mensagens usando um schema genérico em:
`/webhook/generic`

Exemplo:
```json
{
  "id": "evt-1",
  "timestamp": 1710960000000,
  "session": "default",
  "event": "message",
  "message": {
    "id": "msg-1",
    "timestamp": 1710960000,
    "from": "551199999999@c.us",
    "body": "Oi, meu nome é Ana",
    "has_media": false
  }
}
```
