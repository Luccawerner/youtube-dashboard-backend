# 🎨 ADICIONAR CORES NOS CARDS TOP 10

## 🎯 OBJETIVO
Colorir os cards dos TOP 10 Videos (Nossos e Minerados) de acordo com o subniche do canal.

**OPACIDADE:** 20% (cor de fundo suave e elegante)

**EXEMPLO:**
- Vídeo do canal "Relatos Oscuros" → Subniche "Historias Sombrias" → Cor roxa (20% opacidade)

---

## 📝 INSTRUÇÕES - TOP 10 NOSSOS

### PASSO 1: Abrir arquivo
```
src/components/WeeklyReportModal.tsx
```

### PASSO 2: Encontrar esta linha (por volta da linha 158):

```typescript
{data.report_data.top_10_nossos.map((video, index) => {
  const position = index + 1;
  const medal = getMedalEmoji(position);

  return (
```

### PASSO 3: ADICIONAR 1 linha depois de `const medal = getMedalEmoji(position);`

**ADICIONE esta linha:**
```typescript
const cores = obterCorSubnicho(video.canal_subnicho);
```

**Resultado deve ficar assim:**
```typescript
{data.report_data.top_10_nossos.map((video, index) => {
  const position = index + 1;
  const medal = getMedalEmoji(position);
  const cores = obterCorSubnicho(video.canal_subnicho);  // ← NOVA LINHA

  return (
```

### PASSO 4: Encontrar esta linha (logo abaixo):

```typescript
<div
  key={video.video_id}
  className={`flex items-start gap-3 p-3 rounded-lg border ${
    position <= 3 ? 'bg-muted/30 border-primary/50' : ''
  }`}
>
```

### PASSO 5: SUBSTITUIR pelo código abaixo:

```typescript
<div
  key={video.video_id}
  className="flex items-start gap-3 p-3 rounded-lg border-l-4"
  style={{
    backgroundColor: cores.fundo + '20',
    borderLeftColor: cores.borda,
  }}
>
```

**O que mudou:**
- ❌ REMOVIDO: `className` dinâmico com condições
- ✅ ADICIONADO: `border-l-4` na className
- ✅ ADICIONADO: `style` com backgroundColor (opacidade 20%) e borderLeftColor

---

## 📝 INSTRUÇÕES - TOP 10 MINERADOS

### PASSO 6: Encontrar esta linha (por volta da linha 209):

```typescript
{data.report_data.top_10_minerados.map((video, index) => {
  const position = index + 1;
  const medal = getMedalEmoji(position);

  return (
```

### PASSO 7: ADICIONAR 1 linha depois de `const medal = getMedalEmoji(position);`

**ADICIONE esta linha:**
```typescript
const cores = obterCorSubnicho(video.canal_subnicho);
```

**Resultado deve ficar assim:**
```typescript
{data.report_data.top_10_minerados.map((video, index) => {
  const position = index + 1;
  const medal = getMedalEmoji(position);
  const cores = obterCorSubnicho(video.canal_subnicho);  // ← NOVA LINHA

  return (
```

### PASSO 8: Encontrar esta linha (logo abaixo):

```typescript
<div
  key={video.video_id}
  className={`flex items-start gap-3 p-3 rounded-lg border ${
    position <= 3 ? 'bg-muted/30 border-primary/50' : ''
  }`}
>
```

### PASSO 9: SUBSTITUIR pelo código abaixo:

```typescript
<div
  key={video.video_id}
  className="flex items-start gap-3 p-3 rounded-lg border-l-4"
  style={{
    backgroundColor: cores.fundo + '25',
    borderLeftColor: cores.borda,
  }}
>
```

---

## ✅ RESUMO DAS MUDANÇAS

### Em TOP 10 NOSSOS:
1. **Linha 161** (depois de `const medal`): ADICIONAR `const cores = obterCorSubnicho(video.canal_subnicho);`
2. **Linhas 163-167**: SUBSTITUIR o `<div` pelo código com `style`

### Em TOP 10 MINERADOS:
1. **Linha ~212** (depois de `const medal`): ADICIONAR `const cores = obterCorSubnicho(video.canal_subnicho);`
2. **Linhas ~214-218**: SUBSTITUIR o `<div` pelo código com `style`

---

## 🎨 EXEMPLO VISUAL

### ANTES (código atual):
```typescript
{data.report_data.top_10_nossos.map((video, index) => {
  const position = index + 1;
  const medal = getMedalEmoji(position);
  // ← FALTA A LINHA DAS CORES AQUI

  return (
    <div
      key={video.video_id}
      className={`flex items-start gap-3 p-3 rounded-lg border ${
        position <= 3 ? 'bg-muted/30 border-primary/50' : ''
      }`}
      // ← FALTA O STYLE AQUI
    >
```

### DEPOIS (código correto):
```typescript
{data.report_data.top_10_nossos.map((video, index) => {
  const position = index + 1;
  const medal = getMedalEmoji(position);
  const cores = obterCorSubnicho(video.canal_subnicho);  // ✅ ADICIONADO

  return (
    <div
      key={video.video_id}
      className="flex items-start gap-3 p-3 rounded-lg border-l-4"
      style={{                                             // ✅ ADICIONADO
        backgroundColor: cores.fundo + '20',               // ✅ ADICIONADO (opacidade 20%)
        borderLeftColor: cores.borda,                      // ✅ ADICIONADO
      }}                                                   // ✅ ADICIONADO
    >
```

---

## 🔍 COMO FUNCIONA

1. **`video.canal_subnicho`** - Campo que vem do backend (ex: "Historias Sombrias")
2. **`obterCorSubnicho()`** - Função que retorna as cores do subniche
3. **`cores.fundo`** - Cor de fundo (ex: "#7C3AED" para roxo)
4. **`cores.borda`** - Cor da borda (ex: "#5B21B6" para roxo escuro)
5. **`+ '20'`** - Adiciona opacidade 20% (ex: "#7C3AED20")

---

## ✅ VALIDAÇÃO

Depois de aplicar:

1. **Build deve completar sem erros**
2. **Abra o dashboard**
3. **Limpe cache:** Ctrl + Shift + R
4. **Abra Relatório Semanal**
5. **Verifique TOP 10 Nossos:**
   - [ ] Cards têm cor de fundo suave
   - [ ] Borda esquerda colorida (4px)
   - [ ] Cores diferentes para canais de subniches diferentes
   - [ ] Mesma cor para canais do mesmo subniche
6. **Verifique TOP 10 Minerados:**
   - [ ] Cards têm cor de fundo suave
   - [ ] Borda esquerda colorida (4px)
   - [ ] Cores diferentes para canais de subniches diferentes

---

## 🚨 SE DER ERRO

### Erro: "Cannot read property 'fundo' of undefined"
**Causa:** `video.canal_subnicho` está undefined ou `obterCorSubnicho` não encontrou a cor

**Solução:** Adicione fallback:
```typescript
const cores = video.canal_subnicho
  ? obterCorSubnicho(video.canal_subnicho)
  : { fundo: '#666666', borda: '#444444' };
```

### Cores não aparecem
**Causa:** Cache ou build não completou

**Solução:**
1. Limpe cache (Ctrl+Shift+R)
2. Aguarde build completar no Lovable
3. Verifique console (F12) para erros

---

## 🎨 CORES POR SUBNICHE

Quando aplicar, os cards terão estas cores:

| Subniche | Cor de Fundo | Exemplo |
|----------|--------------|---------|
| **Histórias Sombrias** | Roxo (#7C3AED) | Relatos Oscuros |
| **Terror** | Vermelho (#DC2626) | Szepty z Nocy |
| **Relatos de Guerra** | Verde (#059669) | Forgotten Frontlines |
| **Contos Familiares** | Laranja (#F97316) | Voices of Auntie Mae |
| **Pessoas Desaparecidas** | Azul (#0284C7) | Final Moments |
| **Stickman** | Azul Escuro (#2563EB) | simple, actually |

---

## 🎯 RESULTADO ESPERADO

**Cada vídeo TOP 10 terá:**
- ✅ Cor de fundo suave (20% opacidade)
- ✅ Borda esquerda colorida (4px)
- ✅ Cor do subniche do canal
- ✅ Visual profissional e organizado
- ✅ Fácil identificar subniches por cor

---

**São apenas 4 pequenas mudanças (2 linhas em cada TOP 10)!** 🚀
