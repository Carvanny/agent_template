# Prompt de Implementação do Projeto

Crie um projeto Python 3.11+ para uma assistente comercial com arquitetura limpa, foco em estabilidade, baixo acoplamento e pronta para produção inicial.

## Objetivo do sistema
Receber mensagens de WhatsApp via WAHA, processar texto e áudio, usar Agno como orquestrador do agente com Gemini como modelo, manter sessão curta e cache em Redis, persistir somente o resultado final da conversa em SQLite e evitar consumo desnecessário de tokens.

## Requisitos obrigatórios
- framework da API: FastAPI
- validação/configuração: pydantic + pydantic-settings
- env vars e segredos: python-dotenv + .env
- cliente HTTP: httpx
- cache/sessão/deduplicação: redis
- transcrição de áudio: faster-whisper
- orquestração do agente: Agno
- banco local: sqlite3 ou camada simples compatível
- tipagem forte
- testes automatizados
- lint e checagem estática

## Jornadas obrigatórias

### Jornada 1: texto recebido
1. Receber webhook do WAHA.
2. Validar payload e segredo.
3. Deduplicar por message_id no Redis.
4. Verificar sessão por chat_id/cellnumber no Redis.
5. Se não houver sessão ou se tiver passado 24h, consultar SQLite.
6. Antes de chamar a LLM, verificar se já existem dados do lead para evitar perguntas repetidas.
7. Montar contexto com arquivos markdown em `memory/`.
8. Gerar resposta comercial fluida com uma pergunta por vez.
9. Atualizar sessão e resumo no Redis.
10. Persistir no SQLite apenas quando a conversa estiver concluída.

### Jornada 2: áudio recebido
1. Receber webhook do WAHA com mídia.
2. Baixar áudio com segurança.
3. Transcrever com faster-whisper.
4. Normalizar texto transcrito.
5. Reutilizar a mesma jornada de texto a partir da transcrição.

### Jornada 3: cliente já conhecido
1. Se o cliente já existir no Redis ou SQLite, carregar dados principais.
2. Não perguntar novamente o que já estiver preenchido.
3. Atualizar apenas o campo que o cliente pedir para alterar.
4. Evitar nova chamada à LLM quando a atualização puder ser feita por regra simples.

### Jornada 4: baixa confiança
1. Se o agente não souber responder, não inventar.
2. Retornar resposta segura.
3. Direcionar para `faq.html`.
4. Oferecer encaminhamento para humano.

## Arquivos de memória obrigatórios
- `memory/agent_profile.md`
- `memory/agent_guidelines.md`
- `memory/questionario.md`
- `memory/agent_aprendizado.md`

## Regras de negócio
- armazenar no SQLite somente quando a conversa for finalizada
- usar Redis para sessão curta, resumo, deduplicação e cache operacional
- leitura de SQLite deve ocorrer antes de gastar tokens, quando aplicável
- registrar aprendizado em `agent_aprendizado.md` apenas por processo controlado, nunca como escrita irrestrita a cada mensagem

## Boas práticas exigidas
- separar camadas: api, services, repositories, schemas, core
- criar Settings centralizados
- usar timeouts, retries e tratamento de falhas externas
- usar logs estruturados sem vazar segredos
- garantir idempotência no webhook
- criar funções pequenas e coesas
- evitar lógica de prompt espalhada pelo projeto
- isolar integração com WAHA, Redis, Gemini e transcrição em serviços próprios
- escrever testes para texto, áudio, deduplicação, recuperação de lead e fallback de FAQ

## Entregáveis esperados
- estrutura de pastas organizada
- código inicial funcional
- `.env.example`
- `README.md` com instruções de execução
- exemplos de payload do webhook
- testes básicos
- comentários objetivos explicando decisões críticas

## Restrições
- não usar bibliotecas obsoletas
- preferir APIs estáveis e documentadas oficialmente
- manter o projeto simples o suficiente para MVP, mas com base correta para evoluir
