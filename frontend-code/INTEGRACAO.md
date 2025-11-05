# 🚀 GUIA DE INTEGRAÇÃO - ANÁLISE TAB + RELATÓRIO SEMANAL

## 📋 PASSO 1: ADICIONAR TIPOS

Criar arquivo: `src/types/analysis.ts`
- Copiar conteúdo de `types-analysis.ts`

## 📋 PASSO 2: ATUALIZAR API SERVICE

Editar: `src/services/api.ts`

### 2.1 - Adicionar imports no topo:
```typescript
import type {
  KeywordsResponse,
  TitlePatternsResponse,
  TopChannelsResponse,
  SubnichesResponse,
  WeeklyReportResponse,
  WeeklyReport
} from '@/types/analysis';
```

### 2.2 - Adicionar métodos na classe ApiService (antes do fechamento):
- Copiar conteúdo de `api-methods.ts`

## 📋 PASSO 3: ADICIONAR COMPONENTES

Criar os seguintes arquivos:

```
src/components/KeywordsRanking.tsx
src/components/TitlePatternsCarousel.tsx
src/components/TopChannelsCarousel.tsx
src/components/AnalysisTab.tsx
src/components/WeeklyReportModal.tsx
```

Copiar o conteúdo dos arquivos respectivos.

## 📋 PASSO 4: INTEGRAR NO DASHBOARD

Editar: `src/components/Dashboard.tsx`

### 4.1 - Adicionar imports no topo:
```typescript
import { AnalysisTab } from './AnalysisTab';
import { WeeklyReportModal } from './WeeklyReportModal';
import { Bell } from 'lucide-react'; // Se não estiver importado
```

### 4.2 - Adicionar estado para o modal:
```typescript
// Adicionar após outros estados (linhas ~20-30)
const [isReportModalOpen, setIsReportModalOpen] = useState(false);
```

### 4.3 - Adicionar ícone do relatório no header:

Procurar onde está o ícone de notificações e adicionar ao lado:

```typescript
{/* Adicionar após o ícone de notificações */}
<Button
  variant="ghost"
  size="icon"
  className="relative"
  onClick={() => setIsReportModalOpen(true)}
  title="Relatório Semanal"
>
  <Bell className="h-5 w-5" />
</Button>
```

### 4.4 - Adicionar nova Tab "Análise":

Procurar o componente `<Tabs>` e adicionar uma nova `<TabsList>`:

**ANTES:**
```typescript
<TabsList className="grid w-full grid-cols-3">
  <TabsTrigger value="minerados">Canais Minerados</TabsTrigger>
  <TabsTrigger value="nossos">Nossos Canais</TabsTrigger>
  <TabsTrigger value="notificacoes">
    <div className="flex items-center gap-2">
      Notificações
      {notificationStats.unseen > 0 && (
        <Badge variant="destructive" className="ml-1">
          {notificationStats.unseen}
        </Badge>
      )}
    </div>
  </TabsTrigger>
</TabsList>
```

**DEPOIS:**
```typescript
<TabsList className="grid w-full grid-cols-4">
  <TabsTrigger value="minerados">Canais Minerados</TabsTrigger>
  <TabsTrigger value="nossos">Nossos Canais</TabsTrigger>
  <TabsTrigger value="analise">Análise</TabsTrigger>
  <TabsTrigger value="notificacoes">
    <div className="flex items-center gap-2">
      Notificações
      {notificationStats.unseen > 0 && (
        <Badge variant="destructive" className="ml-1">
          {notificationStats.unseen}
        </Badge>
      )}
    </div>
  </TabsTrigger>
</TabsList>
```

### 4.5 - Adicionar conteúdo da nova Tab:

Procurar os `<TabsContent>` e adicionar após a tab "nossos":

```typescript
<TabsContent value="analise" className="mt-6">
  <AnalysisTab />
</TabsContent>
```

### 4.6 - Adicionar o Modal no final do componente (antes do fechamento):

```typescript
{/* Adicionar antes do fechamento do return */}
<WeeklyReportModal
  isOpen={isReportModalOpen}
  onClose={() => setIsReportModalOpen(false)}
/>
```

## 📋 PASSO 5: TESTAR

1. Salvar todas as mudanças
2. Verificar se não há erros de compilação
3. Abrir o navegador
4. Testar a nova aba "Análise"
5. Testar o ícone de relatório semanal (Bell)

## ⚠️ POSSÍVEIS ERROS E SOLUÇÕES

### Erro: "Cannot find module '@/types/analysis'"
**Solução:** Verificar se o arquivo `src/types/analysis.ts` foi criado

### Erro: Componentes não aparecem
**Solução:** Verificar se todos os imports estão corretos no Dashboard.tsx

### Erro: API retorna 404
**Solução:** Verificar se o backend está rodando e se a URL está correta em `api.ts`

### Erro: "date-fns not found"
**Solução:** Instalar dependência:
```bash
npm install date-fns
```

## 🎨 CUSTOMIZAÇÕES OPCIONAIS

### Mudar cores das medalhas:
Editar nos componentes as classes `text-primary`, `text-green-600`, etc.

### Alterar período padrão:
Nos componentes, mudar `useState<7 | 15 | 30>(30)` para o período desejado

### Alterar intervalo de auto-refresh:
No Dashboard.tsx, mudar `staleTime` nos `useQuery`

## 📊 ESTRUTURA FINAL

```
src/
├── types/
│   └── analysis.ts                    ✅ NOVO
├── services/
│   └── api.ts                         ✏️ MODIFICADO
└── components/
    ├── Dashboard.tsx                  ✏️ MODIFICADO
    ├── AnalysisTab.tsx               ✅ NOVO
    ├── KeywordsRanking.tsx           ✅ NOVO
    ├── TitlePatternsCarousel.tsx     ✅ NOVO
    ├── TopChannelsCarousel.tsx       ✅ NOVO
    └── WeeklyReportModal.tsx         ✅ NOVO
```

## 🚀 PRONTO!

Agora você tem:
- ✅ Tab de Análise completa (Keywords, Patterns, Top Channels)
- ✅ Relatório Semanal (modal com todas as seções)
- ✅ Responsividade (desktop + mobile)
- ✅ Mesma identidade visual do projeto
- ✅ Integração com backend 100% funcional
