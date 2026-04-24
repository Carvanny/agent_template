# Guia de Configuração por Cenário

Este guia reúne os cenários mais comuns e o que configurar em cada um deles.

## Variáveis principais (.env)

- `APP_NAME`, `BRAND_NAME`, `FAQ_URL`
- `WAHA_BASE_URL`, `WAHA_API_KEY`, `WAHA_WEBHOOK_SECRET`
- `COMMUNICATION_PROVIDER` (`waha`, `console`, `http`)
- `ALLOW_UNAUTHENTICATED_WEBHOOK` (desliga autenticação do webhook)
- `ALLOW_WEBHOOK_QUERY_SECRET` (permite segredo na query string)

## Cenário 1: WAHA em Docker e App no Host (opção mais comum)

### Passos
1. Garanta que o app está rodando no host:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
2. Configure no `.env`:
   ```env
   WAHA_WEBHOOK_SECRET=seu-segredo
   WHATSAPP_HOOK_URL=http://host.docker.internal:8000/webhook/waha
   ALLOW_WEBHOOK_QUERY_SECRET=false
   ALLOW_UNAUTHENTICATED_WEBHOOK=false
   ```
3. Configure o header no WAHA:
   ```env
   WHATSAPP_HOOK_CUSTOM_HEADERS=x-webhook-secret:seu-segredo
   ```
4. Reinicie o container do WAHA e a sessão.

### Checklist rápido
- `curl http://localhost:8000/health` retorna `200`
- Logs do WAHA mostram `Configuring webhooks for http://host.docker.internal:8000/webhook/waha`
- Logs do app mostram `POST /webhook/waha` com `200`

## Cenário 2: WAHA e App via Docker Compose

### Passos
1. Suba o stack:
   ```bash
   docker compose up -d
   ```
2. No `.env`:
   ```env
   WAHA_WEBHOOK_SECRET=seu-segredo
   ```
3. No `docker-compose.yml` (WAHA):
   ```yaml
   WAHA_WEBHOOK_URL: http://app:8000/webhook/waha
   WHATSAPP_HOOK_CUSTOM_HEADERS: x-webhook-secret:seu-segredo
   ```

## Cenário 3: Sem autenticação no webhook (temporário)

Use apenas em desenvolvimento:
```env
ALLOW_UNAUTHENTICATED_WEBHOOK=true
```

## Cenário 4: WAHA não suporta header (usar query string)

```env
ALLOW_WEBHOOK_QUERY_SECRET=true
WHATSAPP_HOOK_URL=http://host.docker.internal:8000/webhook/waha?secret=seu-segredo
```

## Cenário 5: Provider console (debug local)

```env
COMMUNICATION_PROVIDER=console
```
As respostas são logadas no stdout, sem integração externa.

## Cenário 6: Provider HTTP genérico

```env
COMMUNICATION_PROVIDER=http
COMM_HTTP_SEND_TEXT_URL=https://seu-endpoint/send-text
COMM_HTTP_SEND_SEEN_URL=https://seu-endpoint/send-seen
COMM_HTTP_HEADERS=Authorization: Bearer <token>;X-Api-Key: <key>
```

## Cenário 7: LLM local via LM Studio (Llama 3)

1. No Windows, habilite o servidor do LM Studio (OpenAI compatible API).
2. Pegue o IP do notebook Windows na rede local.
3. Configure no `.env` do app:
   ```env
   LLM_PROVIDER=lmstudio
   OPENAI_LIKE_BASE_URL=http://<IP-WINDOWS>:1234/v1
   OPENAI_LIKE_MODEL=<id-do-modelo>
   OPENAI_LIKE_API_KEY=
   ```
4. Verifique o modelo disponível em `GET /v1/models` no servidor do LM Studio.

## Webhook genérico (entrada)

Endpoint:
```
POST /webhook/generic
```

Payload mínimo:
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

## Idioma por DDI (DDI → idioma)

Defina o mapa:
```env
COUNTRY_LANGUAGE_MAP=55:pt,595:es
```

### Identificador `@lid`
Quando o WAHA envia `@lid`, o número real não está no payload.
O sistema tenta resolver via WAHA LIDs API (`/api/{session}/lids/{lid}`).
Se não resolver, cai para idioma padrão (`pt`).

## Troubleshooting rápido

- `401 Unauthorized`: segredo ausente ou diferente.
- `ECONNREFUSED`: URL do webhook aponta para o lugar errado.
- Nenhum log de webhook: sessão do WAHA não foi reiniciada após mudança.
