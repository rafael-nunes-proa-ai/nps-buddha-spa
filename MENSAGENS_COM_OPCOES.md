# Mensagens com Opções

Este documento descreve o padrão usado pela Kloe para construir mensagens com opções (botões/listas de escolha) que são entregues ao usuário final em qualquer canal (WhatsApp, Telegram, Web, Teams, etc.).

Use esta documentação como contexto para qualquer agente, IA ou serviço que precise gerar respostas com opções respeitando os padrões já existentes no projeto.

## Índice

- [Visão Geral](#visão-geral)
- [Estrutura Canônica](#estrutura-canônica)
- [Anatomia de uma Opção](#anatomia-de-uma-opção)
- [Convenção do Pipe (`|`) no `label`](#convenção-do-pipe--no-label)
- [Onde o `outputOption` é Construído](#onde-o-outputoption-é-construído)
- [Interpolação de Variáveis](#interpolação-de-variáveis-replaceoutput)
- [Tradução por Canal](#tradução-por-canal)
- [Como o Match da Resposta Funciona](#como-o-match-da-resposta-funciona)
- [Padrão Recomendado para Geração](#padrão-recomendado-para-geração)
- [Exemplos](#exemplos)
- [Checklist de Validação](#checklist-de-validação)

---

## Visão Geral

Toda mensagem com opções na Kloe segue **uma única estrutura interna canônica** independente do canal. O canal só importa no momento do envio — a transformação para o formato específico (botões interativos do WhatsApp, lista numerada do Telegram, JSON do front Web, etc.) é feita pelos integrations em `src/services/`.

Isto significa que para gerar uma mensagem com opções:

1. Produza o objeto no **formato canônico** (descrito abaixo).
2. Coloque-o dentro do array `output.generic`.
3. O `channel-router` e os integrations cuidam do resto.

---

## Estrutura Canônica

O template está definido em `src/api/flow.js:33-37`:

```js
const outputOption = {
  response_type: 'option',
  title: '',
  options: []
}
```

Forma final completa:

```js
{
  response_type: 'option',
  title: 'Texto/pergunta exibida acima das opções (string, pode ser vazio)',
  description: 'Opcional — rótulo do botão em listas WhatsApp interativas (>3 opções)',
  options: [
    { label: 'Opção 1', value: { input: { text: 'Opção 1' } } },
    { label: 'Opção 2', value: { input: { text: 'Opção 2' } } }
  ]
}
```

Campos:

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `response_type` | string | Sim | Sempre `'option'` |
| `title` | string | Sim | Texto/pergunta acima das opções. Pode ser `''` |
| `description` | string | Não | Rótulo do botão de abertura em listas WhatsApp |
| `options` | array | Sim | Lista de opções (pelo menos 1) |

---

## Anatomia de uma Opção

Cada item de `options` deve seguir rigidamente este formato (ver `src/api/flow.js:330-343`):

```js
{
  label: 'Texto visível para o usuário',
  value: {
    input: {
      text: 'Texto que retorna como se o usuário tivesse digitado'
    }
  }
}
```

- `label` — o que o usuário vê no botão/item.
- `value.input.text` — o texto que será enviado de volta ao bot quando o usuário clicar. Deve ser **igual ou muito próximo** à parte do `label` antes do `|` (ver matching mais adiante).

---

## Convenção do Pipe (`|`) no `label`

O caractere `|` no `label` separa duas partes:

```
'Texto do botão|Descrição complementar'
```

- **Antes do `|`**: texto principal exibido (botão / título do item).
- **Depois do `|`**: descrição secundária (usada apenas em lista WhatsApp).

Comportamento por canal:

- **WhatsApp lista interativa**: parte antes do `|` vira `title`, parte depois vira `description` (ver `src/services/meta/integration.js:200-210`).
- **WhatsApp botão / canais texto-only / Web**: apenas a parte antes do `|` é exibida (`src/utils/message.js:76`, `src/services/meta/integration.js:160-163`).

---

## Onde o `outputOption` é Construído

Todos os pontos do projeto que produzem opções seguem **exatamente o mesmo formato**:

| Local | Contexto |
|---|---|
| `src/api/flow.js:330-355` | Flow nativo Kloe (dialog node `response_type: 'option'`) |
| `src/api/flow.js:564-580` | Pesquisa de satisfação humano (survey_human) |
| `src/api/flow.js:660-676` | Pesquisa de satisfação bot (survey_bot) |
| `src/api/proax.js:919-933` | LLM agent ProaX retornando opções |
| `src/services/ibm/watson-helpers/data-transformers.js:33-50` | Conversão Watson V2 (`suggestion` → `option`) |
| `src/core/message-core.js:317-321` | Lista de departamentos no atendimento humano |

Sempre o mesmo shape: `{ response_type: 'option', title, options: [{ label, value: { input: { text } } }] }`.

---

## Interpolação de Variáveis (`replaceOutput`)

A função `replaceOutput(userText, textToReplace, context, quotes)` em `src/api/flow.js:98-103` resolve variáveis de contexto antes de entregar a mensagem ao canal. Ela substitui:

- variáveis `<? context.var ?>` ou `{{var}}` (via `utils/template.replaceVariable`)
- a referência especial `input.text` pelo texto digitado pelo usuário
- escapes `\\n` por quebra de linha real

Aplicada automaticamente sobre:

- `title` da opção (`src/api/flow.js:348`)
- cada `label` das opções (`src/api/flow.js:334`)

Ou seja: **basta colocar a variável diretamente no texto que o flow se encarrega da substituição**:

```js
{
  response_type: 'option',
  title: 'Olá <? context.nome ?>, escolha uma opção:',
  options: [
    { label: 'Pedido #<? context.pedidoId ?>', value: { input: { text: 'Ver pedido' } } }
  ]
}
```

---

## Tradução por Canal

A mesma estrutura canônica é traduzida por cada integration:

### WhatsApp (Meta Cloud API)
`src/services/meta/integration.js:144-230`

- **≤ 3 opções** com `hasInteractive` → botões interativos (`interactive.button`). `label` truncado em **20 chars**.
- **4 a 10 opções** com `hasInteractive` → lista interativa (`interactive.list`). `label` em **24 chars** + `description` após `|`. `answer.description` vira o rótulo do botão de abertura.
- **> 10 opções** ou cliente sem `hasInteractive` → texto numerado:
  ```
  Título da pergunta

  1 - Opção 1
  2 - Opção 2
  ```

### Telegram
`src/services/telegram/integration.js:102-116`

Sempre texto numerado (sem botão nativo neste integration).

### Web / App / API
`src/utils/message.js:74-83` e `src/lib/transformers/chat-transformer.js:127-129`

Passa o array `options` direto como JSON estruturado para o front renderizar.

### Outros canais
- Teams (`src/services/teams/integration.js:51`)
- Messenger (`src/services/messenger/integration.js:23`)
- Instagram (`src/services/instagram/integration.js:23`)
- Workplace (`src/services/workplace/integration.js:23`)
- Twilio (`src/services/twilio/integration.js:28`)
- Gupshup v2/v3 (`src/services/gupshup/integration_v2.js:51`, `integration_v3.js:41`)
- Dialog360 (`src/services/dialog360/integration.js:36`)

> **Importante:** ao gerar a mensagem no formato canônico, todos os canais funcionam. Não é necessário se preocupar com formatação por canal.

---

## Como o Match da Resposta Funciona

Quando o usuário clica/digita uma opção, o flow procura o `lastOutput` com `response_type === 'option'` e faz **matching por similaridade Jaccard de palavras** (`src/api/flow.js:411-437`):

1. Normaliza: remove emojis, lowercase, trim.
2. Compara o texto do usuário contra cada `option`:
   - Threshold de **0.7** contra o `label` completo (após normalização).
   - Threshold de **0.7** contra `label.split('|')[0]` (parte antes do pipe).
3. Se nenhum match passar do threshold:
   - Verifica `stopPhrases` (`atendente`, `humano`, `sair`, etc.) → volta para `start`.
   - Caso contrário, exibe `anythingElse` aleatório (`src/api/flow.js:54-60`) e repete a pergunta.

Implicação prática:

- O `value.input.text` deve ser **igual ou muito parecido com a parte do `label` antes do `|`**.
- Frases longas no `label` reduzem a chance de match — prefira labels curtos.
- Frases longas/contexto vão no `title`, **não** no `label`.

---

## Padrão Recomendado para Geração

Para gerar uma mensagem com opções, produza um item dentro de `output.generic` no formato:

```js
{
  response_type: 'option',
  title: 'Pergunta ou contexto da escolha',
  options: [
    { label: 'Sim', value: { input: { text: 'Sim' } } },
    { label: 'Não', value: { input: { text: 'Não' } } }
  ]
}
```

### Regras práticas

| Regra | Motivo |
|---|---|
| `label` ≤ **20 chars** se quiser botão WhatsApp interativo (≤ 3 opções) | Limite da API do WhatsApp |
| `label` ≤ **24 chars** + use `\|descrição` se for lista WhatsApp (4–10 opções) | Limite da API do WhatsApp |
| `value.input.text` igual à parte do `label` antes do `\|` | Garante match Jaccard ≥ 0.7 |
| Frases longas vão no `title`, não no `label` | Match Jaccard usa o label |
| Para interpolar contexto, use `<? context.nome ?>` no `title`/`label` | `replaceOutput` resolve automaticamente |
| Pode combinar `text` + `option` no mesmo `output.generic` | Padrão usado em `message-core.js:312-322` |
| Mínimo 1 opção, máximo recomendado 10 (acima vira texto numerado) | Limites de canais interativos |

### Combinando texto + opções

```js
output.generic = [
  {
    response_type: 'text',
    text: 'Bem-vindo à Kloe!'
  },
  {
    response_type: 'option',
    title: 'Como posso ajudar?',
    options: [
      { label: 'Suporte', value: { input: { text: 'Suporte' } } },
      { label: 'Comercial', value: { input: { text: 'Comercial' } } }
    ]
  }
]
```

---

## Exemplos

### Exemplo 1: Sim/Não (botão interativo no WhatsApp)

```js
{
  response_type: 'option',
  title: 'Deseja confirmar o pedido?',
  options: [
    { label: 'Sim', value: { input: { text: 'Sim' } } },
    { label: 'Não', value: { input: { text: 'Não' } } }
  ]
}
```

### Exemplo 2: Lista de departamentos (lista WhatsApp + texto-only)

```js
{
  response_type: 'option',
  title: 'Selecione o departamento desejado:',
  description: 'Departamentos',
  options: [
    { label: 'Suporte Técnico|Problemas com produtos', value: { input: { text: 'Suporte Técnico' } } },
    { label: 'Financeiro|Boletos e pagamentos', value: { input: { text: 'Financeiro' } } },
    { label: 'Vendas|Novos pedidos', value: { input: { text: 'Vendas' } } },
    { label: 'Pós-Venda|Trocas e devoluções', value: { input: { text: 'Pós-Venda' } } }
  ]
}
```

### Exemplo 3: Opções com variáveis de contexto

```js
{
  response_type: 'option',
  title: 'Olá <? context.nome ?>, qual pedido deseja consultar?',
  options: [
    { label: 'Pedido #<? context.ultimoPedido ?>', value: { input: { text: 'Último pedido' } } },
    { label: 'Outro pedido', value: { input: { text: 'Outro pedido' } } }
  ]
}
```

### Exemplo 4: Pesquisa de satisfação (formato real do projeto)

Extraído de `src/api/flow.js:660-676`:

```js
{
  response_type: 'option',
  title: 'Como você avalia o atendimento?',
  options: [
    { label: 'Ótimo', value: { input: { text: 'good' } } },
    { label: 'Regular', value: { input: { text: 'regular' } } },
    { label: 'Ruim', value: { input: { text: 'bad' } } }
  ]
}
```

---

## Checklist de Validação

Antes de entregar uma mensagem com opções, verifique:

- [ ] `response_type` é exatamente `'option'`
- [ ] `title` é uma string (pode ser `''`, mas o campo precisa existir)
- [ ] `options` é array com pelo menos 1 item
- [ ] Cada item tem `label` (string) e `value.input.text` (string)
- [ ] `value.input.text` corresponde à parte do `label` antes do `|`
- [ ] Labels curtos (≤ 20 chars) se desejar botão WhatsApp
- [ ] Frases longas/contexto estão no `title`, não no `label`
- [ ] Variáveis de contexto usam o formato `<? context.var ?>` ou `{{var}}`
- [ ] Não há emojis ou caracteres especiais que prejudiquem o match Jaccard

---

## Referências de Código

- Estrutura canônica: `src/api/flow.js:33-37`
- Construção da opção no flow: `src/api/flow.js:330-355`
- Match Jaccard da resposta: `src/api/flow.js:411-437`
- `replaceOutput` (interpolação): `src/api/flow.js:98-103`
- Helper de canal texto-only: `src/lib/format-helpers.js:16-34`
- Estrutura de mensagem padronizada: `src/utils/message.js:54-117`
- Integration Meta/WhatsApp: `src/services/meta/integration.js:144-230`
- Integration Telegram: `src/services/telegram/integration.js:102-116`
- Departamentos humano: `src/core/message-core.js:312-322`
