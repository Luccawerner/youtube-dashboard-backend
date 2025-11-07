# 🔧 CORREÇÃO: Ações Recomendadas por Subniche

## ⚠️ PROBLEMA ATUAL
Ações Recomendadas não aparecem nada no dashboard.

## ✅ SOLUÇÃO
Atualizar código para estrutura Dict + adicionar cores por subniche.

---

## 📝 INSTRUÇÕES

### PASSO 1: Abrir o arquivo
```
src/components/WeeklyReportModal.tsx
```

---

### PASSO 2: LOCALIZAR a seção "Ações Recomendadas"

Procure por este trecho (deve estar por volta da linha 380-410):

```typescript
{/* Ações Recomendadas */}
<Card>
  <CardHeader>
    <CardTitle className="flex items-center gap-2">
```

**APAGUE TODA A SEÇÃO** desde `{/* Ações Recomendadas */}` até o `</Card>` final dessa seção.

---

### PASSO 3: COLAR o código novo

Cole este código no lugar:

```typescript
{/* ===== AÇÕES RECOMENDADAS POR SUBNICHE ===== */}
<Card>
  <CardHeader>
    <CardTitle className="flex items-center gap-2">
      <Lightbulb className="h-5 w-5 text-primary" />
      Ações Recomendadas por Subniche
    </CardTitle>
    <div className="text-sm text-muted-foreground">
      Insights estratégicos organizados por categoria de conteúdo
    </div>
  </CardHeader>
  <CardContent>
    <div className="space-y-6">
      {Object.entries(data.report_data.recommended_actions).map(([subniche, subnicheData]) => {
        const cores = obterCorSubnicho(subniche);

        return (
          <div key={subniche} className="space-y-3">
            {/* Header do Subniche */}
            <div
              className="px-4 py-3 rounded-lg border-2 flex items-center justify-between"
              style={{
                backgroundColor: cores.fundo + '20',
                borderColor: cores.borda
              }}
            >
              <div className="flex items-center gap-3">
                <ColoredBadge
                  text={subniche}
                  backgroundColor={cores.fundo}
                  borderColor={cores.borda}
                  className="text-base font-semibold"
                />
                <div className="flex items-center gap-2">
                  {subnicheData.status === 'growing' && (
                    <TrendingUp className="h-4 w-4 text-green-600" />
                  )}
                  {subnicheData.status === 'stable' && (
                    <div className="h-4 w-4 text-blue-600">—</div>
                  )}
                  {subnicheData.status === 'declining' && (
                    <TrendingDown className="h-4 w-4 text-red-600" />
                  )}
                  <span className="text-sm font-medium">
                    {subnicheData.growth_percentage > 0 ? '+' : ''}
                    {subnicheData.growth_percentage.toFixed(1)}%
                  </span>
                </div>
              </div>
              <Badge variant="secondary">
                {subnicheData.recommendations.length} {subnicheData.recommendations.length === 1 ? 'ação' : 'ações'}
              </Badge>
            </div>

            {/* Cards de Recomendações */}
            <div className="space-y-3 ml-4">
              {subnicheData.recommendations.map((rec, idx) => (
                <Card
                  key={idx}
                  className="border-l-4"
                  style={{ borderLeftColor: cores.borda }}
                >
                  <CardContent className="p-4 space-y-3">
                    {/* Cabeçalho da Recomendação */}
                    <div className="flex items-start gap-3">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2 flex-wrap">
                          <Badge
                            variant={
                              rec.priority === 'urgent' ? 'destructive' :
                              rec.priority === 'high' ? 'default' :
                              'secondary'
                            }
                            className="text-xs uppercase"
                          >
                            {rec.priority}
                          </Badge>
                          <Badge variant="outline" className="text-xs">
                            {rec.category}
                          </Badge>
                        </div>
                        <div className="font-semibold text-base">
                          {rec.title}
                        </div>
                      </div>
                    </div>

                    {/* Descrição */}
                    <div className="bg-muted/50 p-3 rounded-lg border">
                      <div className="text-sm">{rec.description}</div>
                    </div>

                    {/* Ações */}
                    <div className="bg-slate-50 dark:bg-slate-900 p-3 rounded-lg border">
                      <div className="text-xs font-semibold text-muted-foreground uppercase mb-2">
                        Ações sugeridas:
                      </div>
                      <div className="text-sm whitespace-pre-line">
                        {rec.action}
                      </div>
                    </div>

                    {/* Métricas */}
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <div className="flex items-center gap-1">
                        <span className="font-medium">Impacto:</span>
                        <span className="font-semibold">{rec.impact}</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <span className="font-medium">Esforço:</span>
                        <span className="font-semibold">{rec.effort}</span>
                      </div>
                      {rec.avg_views && (
                        <div className="flex items-center gap-1">
                          <span className="font-medium">Avg Views:</span>
                          <span className="font-semibold">
                            {rec.avg_views.toLocaleString()}
                          </span>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  </CardContent>
</Card>
```

---

### PASSO 4: Verificar imports

No **TOPO DO ARQUIVO**, verifique se estes imports existem. Se não existirem, adicione:

```typescript
import {
  Lightbulb,
  TrendingUp,
  TrendingDown,
  // ... outros imports que já existem
} from 'lucide-react';
```

---

## ✅ VALIDAÇÃO

Depois de aplicar:

1. **Build deve completar sem erros**
2. **Abra o Relatório Semanal**
3. **Limpe o cache:** Ctrl + Shift + R
4. **Verifique:**
   - [ ] Aparecem 6 subniches (Terror, Historias Sombrias, Contos Familiares, Histórias Aleatórias, Relatos de Guerra, Stickman)
   - [ ] Cada subniche tem header colorido (opacidade 20%)
   - [ ] Growth percentage aparece (+162.9%, +220.2%, etc)
   - [ ] Status icon aparece (TrendingUp/Down)
   - [ ] Cards de recomendações aparecem
   - [ ] Prioridades (URGENT/HIGH/MEDIUM) aparecem

---

## 🚨 SE DER ERRO

### Erro: "Cannot read property 'map' of undefined"
**Causa:** Dados não estão carregados ainda
**Solução:** Adicione verificação:
```typescript
{data?.report_data?.recommended_actions && Object.entries(data.report_data.recommended_actions).map(...)}
```

### Erro: "Object.entries is not a function"
**Causa:** recommended_actions não é um objeto
**Solução:** Backend não está retornado estrutura correta. Me avise!

### Nada aparece
**Causa:** Cache ou build não completou
**Solução:**
1. Limpe cache (Ctrl+Shift+R)
2. Verifique se build completou no Lovable
3. Verifique console do navegador (F12)

---

## 📊 ESTRUTURA DE DADOS ESPERADA

O backend deve retornar:

```json
{
  "recommended_actions": {
    "Terror": {
      "status": "growing",
      "growth_percentage": 162.9,
      "recommendations": [
        {
          "priority": "high",
          "category": "FREQUÊNCIA - AJUSTAR",
          "title": "📅 Frequência de upload baixa",
          "description": "...",
          "action": "...",
          "impact": "ALTO",
          "effort": "Alto"
        }
      ]
    },
    "Historias Sombrias": { ... },
    ...
  }
}
```

---

## 🎨 RESULTADO ESPERADO

**Ações Recomendadas com:**
- ✅ 6 subniches visíveis
- ✅ Headers coloridos (opacidade 20%)
- ✅ Bordas coloridas
- ✅ Status e growth percentage
- ✅ Cards de recomendações organizados
- ✅ Badges de prioridade coloridos
- ✅ Visual limpo e profissional

---

**Aplique este código e me avise se funcionou!** 🚀
