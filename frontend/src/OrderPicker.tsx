import { useCallback, useEffect, useMemo, useState } from 'react'

/**
 * The desktop half of the weekly shop: turning a walked list into a nemlig basket.
 *
 * The app deliberately never talks to nemlig. Search needs a bearer token plus
 * session parameters that only exist inside a logged-in tab, and the basket
 * authenticates on a large rotating HttpOnly cookie set. So this screen hands
 * out a snippet to run in that tab and takes the answer back. The token stays
 * in the browser where it was minted, and nothing about the session is stored.
 */

type Candidate = {
  product_id: string
  name: string
  pack: string
  price: number | null
  image: string
  unit_price: string
  fav: boolean
  previous: boolean
  from_memory: boolean
}

type Action = 'buy' | 'link' | 'have_it' | 'not_this_week' | 'unavailable' | 'undecided'

type OrderItem = {
  id: number
  ingredient: string
  need: string
  recipes: string[]
  zone: string
  status: 'mapped' | 'stocked' | 'new'
  query: string | null
  candidates: Candidate[]
  warning: string
  action: Action | null
  product_id: string | null
  product: Candidate | null
  qty: number
  note: string
  url: string
}

type Order = {
  id: number
  run_id: number | null
  source: string
  created_at: string | null
  recorded_at: string | null
  decided: number
  total: number
  items: OrderItem[]
}

type BasketLine = {
  product_id: string
  product_name: string
  pack: string
  price: number
  qty: number
  covers: string[]
  zone: string
}

type BasketPlan = {
  lines: BasketLine[]
  merged: BasketLine[]
  unresolved: Array<{ ingredient: string; reason: string }>
  declined: number
}

type Reconciliation = {
  ok: boolean
  sold_out: Array<BasketLine & { basket_name?: string }>
  missing: BasketLine[]
  mismatched: Array<BasketLine & { basket_qty: number }>
  total: number | null
  product_count: number | null
}

type RunSummary = { id: number; menu: string; checked: number; total: number }

type Props = {
  apiBase: string
  pushToast: (kind: 'success' | 'error' | 'info', message: string) => void
}

/** Declining options, kept apart so each records something different. */
const DECLINE: Array<{ action: Action; label: string; hint: string }> = [
  { action: 'have_it', label: 'Have it', hint: 'Remembered as a kitchen staple' },
  { action: 'not_this_week', label: 'Not this week', hint: 'Changes nothing, teaches nothing' },
  { action: 'unavailable', label: 'Sold out', hint: 'Recorded as an open question, not a staple' },
  { action: 'undecided', label: 'Decide later', hint: 'Kept on the list for next time' },
]

const money = (value: number | null | undefined) =>
  typeof value === 'number' ? `${value.toFixed(2).replace('.', ',')} kr` : ''

/**
 * A console snippet that runs the searches inside the logged-in tab.
 *
 * It harvests the session parameters from a search the site itself has already
 * made, because they cannot be guessed and a bare query returns a 500 that
 * reads exactly like an auth failure.
 */
function searchSnippet(queries: string[]): string {
  return `(async () => {
  const QUERIES = ${JSON.stringify(queries)};
  const ref = performance.getEntriesByType('resource').map(e => e.name)
    .find(n => n.includes('searchgateway/api/search'));
  if (!ref) return console.error('Search for something on nemlig first, then run this again.');
  const params = new URL(ref).searchParams;
  const token = (await (await fetch('/webapi/Token', { credentials: 'include' })).json()).access_token;
  const out = {};
  for (const q of QUERIES) {
    const url = new URL('https://webapi.prod.knl.nemlig.it/searchgateway/api/search');
    params.forEach((v, k) => url.searchParams.set(k, v));
    url.searchParams.set('query', q);
    url.searchParams.set('take', '8');
    url.searchParams.set('skip', '0');
    const r = await fetch(url, { headers: { Authorization: 'Bearer ' + token } });
    out[q] = r.ok ? ((await r.json()).Products?.Products ?? []) : [];
    console.log(out[q].length, q);
    await new Promise(s => setTimeout(s, 120));
  }
  copy(JSON.stringify({ results: out }));
  console.log('Copied. Paste it back into the app.');
})()`
}

/**
 * A console snippet that fills the basket and reports what actually landed.
 *
 * ``AffectPartialQuantity: true`` makes the quantity absolute, so re-running
 * after a crash is safe rather than doubling the order. Only the three fields
 * the app needs come back, so no address or account details leave the tab.
 */
function basketSnippet(lines: BasketLine[]): string {
  const payload = lines.map((line) => ({ id: line.product_id, qty: line.qty, name: line.product_name }))
  return `(async () => {
  const LINES = ${JSON.stringify(payload)};
  for (const l of LINES) {
    const r = await fetch('/webapi/basket/AddToBasket', {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ProductId: l.id, quantity: l.qty, AffectPartialQuantity: true, disableQuantityValidation: false }),
    });
    console.log(r.status, 'x' + l.qty, l.name);
    await new Promise(s => setTimeout(s, 200));
  }
  const b = await (await fetch('/webapi/basket/GetBasket', { credentials: 'include' })).json();
  copy(JSON.stringify({ basket: {
    Lines: (b.Lines || []).map(l => ({ ProductId: l.ProductId, Quantity: l.Quantity, Name: l.Name })),
    TotalProductsPrice: b.TotalProductsPrice, NumberOfProducts: b.NumberOfProducts,
  } }));
  console.log('Basket copied. Paste it back to check what really landed.');
})()`
}

function Snippet({ code, label }: { code: string; label: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="rounded-2xl border border-white/10 bg-brand-dark/60">
      <div className="flex items-center justify-between gap-3 border-b border-white/10 px-4 py-2">
        <span className="text-xs uppercase tracking-[0.2em] text-white/40">{label}</span>
        <button
          type="button"
          onClick={() => {
            void navigator.clipboard.writeText(code)
            setCopied(true)
            window.setTimeout(() => setCopied(false), 1500)
          }}
          className="rounded-full border border-white/15 px-3 py-1 text-xs text-white/70 transition hover:text-white"
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="max-h-40 overflow-auto px-4 py-3 text-[11px] leading-relaxed text-white/60">{code}</pre>
    </div>
  )
}

function Paste({
  label,
  placeholder,
  onSubmit,
  busy,
}: {
  label: string
  placeholder: string
  onSubmit: (parsed: unknown) => void
  busy: boolean
}) {
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)

  return (
    <div className="space-y-2">
      <textarea
        value={text}
        onChange={(event) => {
          setText(event.target.value)
          setError(null)
        }}
        rows={3}
        placeholder={placeholder}
        className="w-full rounded-2xl border border-white/10 bg-brand-dark/50 px-4 py-3 font-mono text-xs text-white/80 focus:border-brand-accent focus:outline-none"
      />
      {error && <p className="text-xs text-red-300">{error}</p>}
      <button
        type="button"
        disabled={!text.trim() || busy}
        onClick={() => {
          try {
            onSubmit(JSON.parse(text))
            setText('')
          } catch {
            setError('That is not valid JSON. Copy the whole clipboard contents.')
          }
        }}
        className="rounded-full bg-brand-accent px-5 py-2 text-sm font-medium text-brand-dark transition disabled:opacity-40"
      >
        {busy ? 'Working…' : label}
      </button>
    </div>
  )
}

export default function OrderPicker({ apiBase, pushToast }: Props) {
  const [orders, setOrders] = useState<Order[]>([])
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [order, setOrder] = useState<Order | null>(null)
  const [basket, setBasket] = useState<BasketPlan | null>(null)
  const [reconciliation, setReconciliation] = useState<Reconciliation | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const call = useCallback(
    async <T,>(path: string, init?: RequestInit): Promise<T> => {
      const response = await fetch(`${apiBase}${path}`, {
        ...init,
        headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
      })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`)
      return body as T
    },
    [apiBase],
  )

  const refreshLists = useCallback(async () => {
    try {
      const [orderBody, runBody] = await Promise.all([
        call<{ orders: Order[] }>('/api/orders'),
        call<{ runs: RunSummary[] }>('/api/runs'),
      ])
      setOrders(orderBody.orders ?? [])
      setRuns(runBody.runs ?? [])
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load orders')
    }
  }, [call])

  useEffect(() => {
    void refreshLists()
  }, [refreshLists])

  const loadBasket = useCallback(
    async (orderId: number) => {
      try {
        setBasket(await call<BasketPlan>(`/api/orders/${orderId}/basket`))
      } catch {
        /* the basket panel is advisory; a failure here must not block picking */
      }
    },
    [call],
  )

  const openOrder = useCallback(
    async (orderId: number) => {
      setBusy(true)
      try {
        const body = await call<Order>(`/api/orders/${orderId}`)
        setOrder(body)
        setReconciliation(null)
        await loadBasket(orderId)
      } catch (caught) {
        pushToast('error', caught instanceof Error ? caught.message : 'Could not open that order')
      } finally {
        setBusy(false)
      }
    },
    [call, loadBasket, pushToast],
  )

  const startOrder = useCallback(
    async (runId: number) => {
      setBusy(true)
      try {
        const body = await call<Order>('/api/orders', {
          method: 'POST',
          body: JSON.stringify({ run_id: runId }),
        })
        setOrder(body)
        setBasket(null)
        setReconciliation(null)
        await refreshLists()
        pushToast('success', `${body.total} items to order`)
      } catch (caught) {
        pushToast('error', caught instanceof Error ? caught.message : 'Could not start an order')
      } finally {
        setBusy(false)
      }
    },
    [call, refreshLists, pushToast],
  )

  const patchItem = useCallback(
    async (itemId: number, patch: Record<string, unknown>) => {
      // Optimistic: choosing forty products should not feel like forty waits.
      setOrder((previous) =>
        previous
          ? {
              ...previous,
              items: previous.items.map((item) =>
                item.id === itemId ? { ...item, ...(patch as Partial<OrderItem>) } : item,
              ),
            }
          : previous,
      )
      try {
        const body = await call<Order>(`/api/orders/items/${itemId}`, {
          method: 'PATCH',
          body: JSON.stringify(patch),
        })
        setOrder(body)
        void loadBasket(body.id)
      } catch (caught) {
        pushToast('error', caught instanceof Error ? caught.message : 'Could not save that')
        if (order) void openOrder(order.id)
      }
    },
    [call, loadBasket, openOrder, order, pushToast],
  )

  const queries = useMemo(() => {
    if (!order) return []
    const seen = new Set<string>()
    for (const item of order.items) {
      if (!item.action && item.query) seen.add(item.query)
    }
    return [...seen]
  }, [order])

  const zones = useMemo(() => {
    if (!order) return []
    const grouped: Array<{ zone: string; items: OrderItem[] }> = []
    for (const item of order.items) {
      if (!grouped.length || grouped[grouped.length - 1].zone !== item.zone) {
        grouped.push({ zone: item.zone, items: [] })
      }
      grouped[grouped.length - 1].items.push(item)
    }
    return grouped
  }, [order])

  if (!order) {
    return (
      <section className="rounded-panel bg-brand-surface/80 p-5 shadow-panel backdrop-blur lg:p-6">
        <h2 className="text-lg font-semibold text-white">Order the rest from nemlig</h2>
        <p className="mt-1 max-w-2xl text-sm text-white/50">
          Walk the list in the kitchen first. Whatever is still unticked is what needs buying,
          and that is what an order starts from.
        </p>

        {error && (
          <p className="mt-4 rounded-2xl border border-red-400/30 bg-red-500/10 p-4 text-sm text-red-200">
            {error}
          </p>
        )}

        <h3 className="mt-6 text-xs uppercase tracking-[0.2em] text-white/40">Start from a walked list</h3>
        <ul className="mt-3 space-y-2">
          {runs.map((run) => (
            <li key={run.id}>
              <button
                type="button"
                disabled={busy}
                onClick={() => void startOrder(run.id)}
                className="flex w-full items-center justify-between gap-3 rounded-2xl border border-white/10 bg-brand-dark/40 px-4 py-3 text-left transition hover:border-brand-accent/60 disabled:opacity-40"
              >
                <span className="truncate font-medium text-white">{run.menu}</span>
                <span className="shrink-0 text-xs text-white/50">
                  {run.total - run.checked} to buy · {run.checked} ticked off
                </span>
              </button>
            </li>
          ))}
          {!runs.length && <li className="text-sm text-white/50">No runs yet. Start one from the Shop tab.</li>}
        </ul>

        {orders.length > 0 && (
          <>
            <h3 className="mt-8 text-xs uppercase tracking-[0.2em] text-white/40">Or pick up where you left off</h3>
            <ul className="mt-3 space-y-2">
              {orders.map((entry) => (
                <li key={entry.id}>
                  <button
                    type="button"
                    onClick={() => void openOrder(entry.id)}
                    className="flex w-full items-center justify-between gap-3 rounded-2xl border border-white/10 bg-brand-dark/40 px-4 py-3 text-left transition hover:border-brand-accent/60"
                  >
                    <span className="min-w-0">
                      <span className="block truncate font-medium text-white">{entry.source || `Order ${entry.id}`}</span>
                      <span className="block text-xs text-white/50">
                        {entry.created_at ? new Date(entry.created_at).toLocaleString() : ''}
                        {entry.recorded_at ? ' · recorded' : ''}
                      </span>
                    </span>
                    <span className="shrink-0 text-xs text-white/50">
                      {entry.decided}/{entry.total} decided
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    )
  }

  const remaining = order.total - order.decided

  return (
    <section className="rounded-panel bg-brand-surface/80 p-4 shadow-panel backdrop-blur lg:p-6">
      <div className="sticky-safe sticky top-0 z-20 -mx-4 mb-4 border-b border-white/10 bg-brand-surface/95 px-4 py-3 backdrop-blur lg:-mx-6 lg:px-6">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => {
              setOrder(null)
              setBasket(null)
              setReconciliation(null)
              void refreshLists()
            }}
            aria-label="Back to order list"
            className="rounded-full border border-white/15 px-3 py-2 text-sm text-white/70 hover:text-white"
          >
            ←
          </button>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-white">{order.source || `Order ${order.id}`}</p>
            <p className="text-xs text-white/50">
              {remaining ? `${remaining} still to decide` : 'every row decided'} · {order.decided}/{order.total}
            </p>
          </div>
        </div>
        <div
          role="progressbar"
          aria-valuenow={order.decided}
          aria-valuemin={0}
          aria-valuemax={order.total}
          className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10"
        >
          <div
            className="h-full rounded-full bg-brand-accent transition-all"
            style={{ width: `${order.total ? (order.decided / order.total) * 100 : 0}%` }}
          />
        </div>
      </div>

      {/* Step 1 -- searches, run in the tab that has the session */}
      {queries.length > 0 && (
        <details open={!order.items.some((item) => item.candidates.length)} className="mb-5">
          <summary className="cursor-pointer text-sm font-semibold text-white">
            1 · Search nemlig for {queries.length} {queries.length === 1 ? 'thing' : 'things'}
          </summary>
          <div className="mt-3 space-y-3">
            <p className="text-xs text-white/50">
              Open nemlig.com logged in, search for anything once so the site reveals its session
              parameters, then paste this into the browser console. Your token never leaves that tab.
            </p>
            <Snippet label="Run in the nemlig console" code={searchSnippet(queries)} />
            <Paste
              label="Load search results"
              placeholder='{"results": { "gulerødder": [ … ] }}'
              busy={busy}
              onSubmit={(parsed) => {
                setBusy(true)
                void call<{ without_candidates: string[]; order: Order }>(
                  `/api/orders/${order.id}/search-results`,
                  { method: 'POST', body: JSON.stringify(parsed) },
                )
                  .then((body) => {
                    setOrder(body.order)
                    if (body.without_candidates.length) {
                      pushToast(
                        'info',
                        `No hits for ${body.without_candidates.join(', ')} — try a different word`,
                      )
                    } else {
                      pushToast('success', 'Products loaded')
                    }
                  })
                  .catch((caught) => pushToast('error', caught.message))
                  .finally(() => setBusy(false))
              }}
            />
          </div>
        </details>
      )}

      {/* Step 2 -- the choices themselves */}
      <div className="space-y-6">
        {zones.map(({ zone, items }) => (
          <div key={zone}>
            <h3 className="mb-2 text-xs uppercase tracking-[0.2em] text-white/40">{zone}</h3>
            <ul className="space-y-3">
              {items.map((item) => (
                <li
                  key={item.id}
                  className={`rounded-2xl border p-4 transition ${
                    item.action === 'buy' || item.action === 'link'
                      ? 'border-brand-accent/50 bg-brand-dark/50'
                      : item.action
                        ? 'border-white/10 bg-brand-dark/20 opacity-60'
                        : 'border-white/10 bg-brand-dark/40'
                  }`}
                >
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <span className="font-medium text-white">{item.ingredient}</span>
                    <span className="text-sm text-amber-300/90">{item.need}</span>
                    {item.status === 'stocked' && (
                      <span className="rounded-full bg-amber-400/15 px-2 py-0.5 text-[11px] text-amber-200">
                        usually have
                      </span>
                    )}
                    {item.query === null && (
                      <span className="rounded-full bg-white/10 px-2 py-0.5 text-[11px] text-white/60">
                        not searchable — paste a link
                      </span>
                    )}
                    {item.recipes.length > 0 && (
                      <span className="text-xs text-white/40">{item.recipes.join(', ')}</span>
                    )}
                  </div>
                  {item.warning && (
                    <p className="mt-1 text-xs text-amber-300/80">⚠ {item.warning}</p>
                  )}

                  {item.candidates.length > 0 && (
                    <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                      {item.candidates.map((candidate) => {
                        const chosen = item.product_id === candidate.product_id && item.action === 'buy'
                        return (
                          <button
                            key={candidate.product_id}
                            type="button"
                            onClick={() =>
                              void patchItem(item.id, {
                                action: 'buy',
                                product_id: candidate.product_id,
                                product: candidate,
                              })
                            }
                            className={`flex gap-3 rounded-xl border p-2 text-left transition ${
                              chosen
                                ? 'border-brand-accent bg-brand-accent/10'
                                : 'border-white/10 hover:border-white/30'
                            }`}
                          >
                            {candidate.image ? (
                              <img
                                src={candidate.image}
                                alt=""
                                loading="lazy"
                                className="h-14 w-14 shrink-0 rounded-lg bg-white/5 object-contain"
                              />
                            ) : (
                              <div className="h-14 w-14 shrink-0 rounded-lg bg-white/5" />
                            )}
                            <span className="min-w-0 flex-1">
                              <span className="flex flex-wrap items-center gap-1">
                                {candidate.previous && (
                                  <span className="rounded-full bg-brand-accent px-1.5 text-[10px] font-semibold text-brand-dark">
                                    {candidate.from_memory ? 'last time' : 'last time'}
                                  </span>
                                )}
                                {candidate.fav && !candidate.previous && (
                                  <span className="text-[10px] text-amber-300">★ bought before</span>
                                )}
                              </span>
                              <span className="block truncate text-xs text-white">{candidate.name}</span>
                              <span className="block truncate text-[11px] text-white/40">{candidate.pack}</span>
                              <span className="block text-[11px] text-white/70">
                                {money(candidate.price)}
                                {candidate.unit_price ? ` · ${candidate.unit_price}` : ''}
                              </span>
                            </span>
                          </button>
                        )
                      })}
                    </div>
                  )}

                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <label className="flex items-center gap-2 text-xs text-white/50">
                      Qty
                      <input
                        type="number"
                        min={1}
                        value={item.qty}
                        onChange={(event) =>
                          void patchItem(item.id, { qty: Math.max(1, Number(event.target.value) || 1) })
                        }
                        className="w-16 rounded-lg border border-white/10 bg-brand-dark/60 px-2 py-1 text-center text-sm text-white"
                      />
                    </label>

                    {DECLINE.map(({ action, label, hint }) => (
                      <button
                        key={action}
                        type="button"
                        title={hint}
                        onClick={() =>
                          void patchItem(item.id, { action: item.action === action ? null : action })
                        }
                        className={`rounded-full border px-3 py-1 text-xs transition ${
                          item.action === action
                            ? 'border-brand-accent bg-brand-accent text-brand-dark'
                            : 'border-white/15 text-white/60 hover:text-white'
                        }`}
                      >
                        {label}
                      </button>
                    ))}

                    <input
                      type="url"
                      defaultValue={item.url}
                      placeholder="or paste a nemlig link"
                      onBlur={(event) => {
                        const value = event.target.value.trim()
                        if (value === item.url) return
                        const match = value.match(/(\d{5,})\s*$/)
                        // A pasted link beats every heuristic: nemlig's own
                        // search cannot reach some products at all.
                        void patchItem(item.id, {
                          url: value,
                          ...(match ? { action: 'link', product_id: match[1] } : {}),
                        })
                      }}
                      className="min-w-[12rem] flex-1 rounded-lg border border-white/10 bg-brand-dark/60 px-3 py-1 text-xs text-white/80"
                    />
                    <input
                      type="text"
                      defaultValue={item.note}
                      placeholder="note for next time"
                      onBlur={(event) => {
                        if (event.target.value === item.note) return
                        void patchItem(item.id, { note: event.target.value })
                      }}
                      className="min-w-[12rem] flex-1 rounded-lg border border-white/10 bg-brand-dark/60 px-3 py-1 text-xs text-white/80"
                    />
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {/* Step 3 -- the basket, and what actually landed in it */}
      {basket && (
        <div className="mt-8 rounded-2xl border border-white/10 bg-brand-dark/40 p-4">
          <h3 className="text-sm font-semibold text-white">
            2 · Fill the basket — {basket.lines.length} lines
          </h3>

          {basket.merged.length > 0 && (
            <p className="mt-2 rounded-xl border border-amber-400/30 bg-amber-500/10 p-3 text-xs text-amber-100">
              Quantities summed where rows share a product:{' '}
              {basket.merged.map((line) => `${line.covers.join(' + ')} → ×${line.qty}`).join('; ')}.
              Posting them separately would leave one pack, not two.
            </p>
          )}
          {basket.unresolved.length > 0 && (
            <p className="mt-2 rounded-xl border border-red-400/30 bg-red-500/10 p-3 text-xs text-red-200">
              Not ready: {basket.unresolved.map((row) => `${row.ingredient} (${row.reason})`).join('; ')}
            </p>
          )}

          {basket.lines.length > 0 && (
            <div className="mt-3 space-y-3">
              <Snippet label="Run in the nemlig console" code={basketSnippet(basket.lines)} />
              <Paste
                label="Check what landed"
                placeholder='{"basket": { "Lines": [ … ] }}'
                busy={busy}
                onSubmit={(parsed) => {
                  setBusy(true)
                  void call<Reconciliation>(`/api/orders/${order.id}/reconcile`, {
                    method: 'POST',
                    body: JSON.stringify(parsed),
                  })
                    .then(setReconciliation)
                    .catch((caught) => pushToast('error', caught.message))
                    .finally(() => setBusy(false))
                }}
              />
            </div>
          )}

          {reconciliation && (
            <div
              className={`mt-3 rounded-xl border p-3 text-xs ${
                reconciliation.ok
                  ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-100'
                  : 'border-red-400/30 bg-red-500/10 text-red-200'
              }`}
            >
              {reconciliation.ok ? (
                <p>
                  Everything landed. {reconciliation.product_count} products,{' '}
                  {money(reconciliation.total)}.
                </p>
              ) : (
                <ul className="space-y-1">
                  {reconciliation.sold_out.map((line) => (
                    <li key={`s${line.product_id}`}>
                      Sold out, basket line is empty: {line.product_name} — a 200 from AddToBasket
                      does not mean you got it.
                    </li>
                  ))}
                  {reconciliation.missing.map((line) => (
                    <li key={`m${line.product_id}`}>Never arrived: {line.product_name}</li>
                  ))}
                  {reconciliation.mismatched.map((line) => (
                    <li key={`q${line.product_id}`}>
                      {line.product_name}: asked for {line.qty}, basket has {line.basket_qty}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      {/* Step 4 -- what the week taught us */}
      <div className="mt-6 rounded-2xl border border-white/10 bg-brand-dark/40 p-4">
        <h3 className="text-sm font-semibold text-white">3 · Remember this for next week</h3>
        <p className="mt-1 text-xs text-white/50">
          Writes the chosen products, quantities and notes back into the product map, and adds
          anything marked “Have it” to the kitchen staples. Keeps one backup.
          {order.recorded_at && ' Already recorded once.'}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {[
            { label: 'Preview', dry: true },
            { label: order.recorded_at ? 'Record again' : 'Record', dry: false },
          ].map(({ label, dry }) => (
            <button
              key={label}
              type="button"
              disabled={busy}
              onClick={() => {
                setBusy(true)
                void call<{
                  added: number
                  updated: number
                  learned_staples: string[]
                  cleared_unresolved: string[]
                }>(`/api/orders/${order.id}/record`, {
                  method: 'POST',
                  body: JSON.stringify({ dry_run: dry }),
                })
                  .then((result) => {
                    const parts = [`${result.added} new, ${result.updated} updated`]
                    if (result.learned_staples.length) {
                      parts.push(`staples: ${result.learned_staples.join(', ')}`)
                    }
                    if (result.cleared_unresolved.length) {
                      parts.push(`resolved: ${result.cleared_unresolved.join(', ')}`)
                    }
                    pushToast(dry ? 'info' : 'success', `${dry ? 'Would write' : 'Wrote'} — ${parts.join(' · ')}`)
                    if (!dry) void openOrder(order.id)
                  })
                  .catch((caught) => pushToast('error', caught.message))
                  .finally(() => setBusy(false))
              }}
              className={`rounded-full px-5 py-2 text-sm font-medium transition disabled:opacity-40 ${
                dry
                  ? 'border border-white/15 text-white/70 hover:text-white'
                  : 'bg-brand-accent text-brand-dark'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </section>
  )
}
