import { useCallback, useEffect, useMemo, useState } from 'react'

/**
 * The desktop half of the weekly shop: turning a walked list into a nemlig basket.
 *
 * The app deliberately never authenticates to nemlig itself. Search needs a
 * bearer token plus session parameters that only exist inside a logged-in tab,
 * and the basket authenticates on a large rotating HttpOnly cookie set. So the
 * backend drives the tab the user is already logged into, over the Chrome
 * DevTools Protocol, and only the results come back. The token stays in the
 * browser where it was minted; nothing about the session is stored here.
 *
 * This screen is desktop-only on purpose: comparing product photographs side
 * by side is the one part of the week that a phone is bad at.
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
  shortfall: Shortfall | null
}

/** The chosen product does not add up to what the week needs. */
type Shortfall = {
  kind: 'short' | 'kinds'
  need: string
  required: number
  bought: number
  family?: string
  message: string
}

/** Two or more rows resolved to the same product and will be merged. */
type Collision = {
  product_id: string
  product_name: string
  pack: string
  ingredients: string[]
  combined_need: string
  total_qty: number
  message: string
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
  collisions: Collision[]
  shortfalls: Array<{ ingredient: string } & Shortfall>
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
  /** In the basket but not on this list: the user's own extras, or a surprise. */
  unexpected?: Array<{ product_id: string; name: string; qty: number; price: number | null }>
  total: number | null
  product_count: number | null
}

/** Whether the backend can reach a logged-in nemlig tab, and why not if it can't. */
type BrowserStatus = { reachable: boolean; tab: string | null; detail: string }

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
 * Why the browser cannot be driven, and what to do about it.
 *
 * Every one of these is something only the user can fix, so the text is the
 * whole point of the component.
 */
function BrowserNotice({
  status,
  onRecheck,
}: {
  status: BrowserStatus | null
  onRecheck: () => void
}) {
  if (!status || (status.reachable && status.tab)) return null
  return (
    <div className="mt-3 flex flex-wrap items-center gap-3 rounded-xl border border-amber-400/30 bg-amber-500/10 p-3 text-xs text-amber-100">
      <span className="min-w-0 flex-1">{status.detail}</span>
      <button
        type="button"
        onClick={onRecheck}
        className="shrink-0 rounded-full border border-amber-200/40 px-3 py-1 text-amber-100 transition hover:text-white"
      >
        Check again
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
  const [browser, setBrowser] = useState<BrowserStatus | null>(null)
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

  const checkBrowser = useCallback(async () => {
    try {
      setBrowser(await call<BrowserStatus>('/api/browser/status'))
    } catch {
      // The notice is advisory; failing to fetch it must not block picking.
    }
  }, [call])

  useEffect(() => {
    void refreshLists()
    void checkBrowser()
  }, [refreshLists, checkBrowser])

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

  const runSearch = useCallback(async () => {
    if (!order) return
    setBusy(true)
    try {
      const body = await call<{ searched: number; without_candidates: string[]; order: Order }>(
        `/api/orders/${order.id}/run-search`,
        { method: 'POST', body: '{}' },
      )
      setOrder(body.order)
      if (body.without_candidates.length) {
        pushToast('info', `No hits for ${body.without_candidates.join(', ')} — try a different word`)
      } else {
        pushToast('success', `Searched ${body.searched} things`)
      }
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : 'Search failed'
      pushToast('error', message)
      void checkBrowser()
    } finally {
      setBusy(false)
    }
  }, [call, order, pushToast, checkBrowser])

  const fillBasket = useCallback(async () => {
    if (!order) return
    setBusy(true)
    try {
      const body = await call<{
        failed: Array<{ product_name: string }>
        reconciliation: Reconciliation
      }>(`/api/orders/${order.id}/fill-basket`, { method: 'POST', body: '{}' })
      setReconciliation(body.reconciliation)
      if (body.failed.length) {
        pushToast('error', `${body.failed.length} lines were refused by nemlig`)
      } else if (body.reconciliation.ok) {
        pushToast('success', 'Basket filled')
      } else {
        pushToast('info', 'Basket filled, but check the report below')
      }
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : 'Could not fill the basket'
      pushToast('error', message)
      void checkBrowser()
    } finally {
      setBusy(false)
    }
  }, [call, order, pushToast, checkBrowser])

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

      {/* Anything that will quietly go wrong at delivery, surfaced before the
          basket is filled rather than discovered a week later. */}
      {(order.shortfalls.length > 0 || order.collisions.length > 0) && (
        <div
          className="mb-5 rounded-2xl border border-rose-400/30 bg-rose-500/10 p-4"
          data-testid="order-warnings"
        >
          <p className="text-sm font-semibold text-rose-200">
            {order.shortfalls.length + order.collisions.length} thing
            {order.shortfalls.length + order.collisions.length === 1 ? '' : 's'} worth a second look
          </p>

          {order.collisions.length > 0 && (
            <ul className="mt-2 space-y-1">
              {order.collisions.map((collision) => (
                <li key={collision.product_id} className="text-xs text-rose-100/90">
                  <span className="font-medium">{collision.ingredients.join(' + ')}</span>{' '}
                  both resolve to {collision.product_name || collision.product_id} — buying{' '}
                  {collision.total_qty} for a combined need of {collision.combined_need || '?'}
                </li>
              ))}
            </ul>
          )}

          {order.shortfalls.length > 0 && (
            <ul className="mt-2 space-y-1">
              {order.shortfalls.map((shortfall) => (
                <li key={shortfall.ingredient} className="text-xs text-rose-100/90">
                  <span className="font-medium">{shortfall.ingredient}</span> — {shortfall.message}
                </li>
              ))}
            </ul>
          )}

          <p className="mt-2 text-[11px] text-rose-200/60">
            Quantities are never changed automatically — these are only worth knowing about.
          </p>
        </div>
      )}

      {/* Step 1 -- searches, run in the tab that already has the session */}
      {queries.length > 0 && (
        <div className="mb-5 rounded-2xl border border-white/10 bg-brand-dark/40 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-white">
                1 · Search nemlig for {queries.length} {queries.length === 1 ? 'thing' : 'things'}
              </p>
              <p className="mt-1 text-xs text-white/50">
                Runs in your logged-in nemlig tab. Your token stays in the browser.
              </p>
            </div>
            <button
              type="button"
              disabled={busy || browser?.reachable === false}
              onClick={() => void runSearch()}
              className="rounded-full bg-brand-accent px-5 py-2 text-sm font-medium text-brand-dark transition disabled:opacity-40"
            >
              {busy ? 'Searching…' : 'Search nemlig'}
            </button>
          </div>
          <BrowserNotice status={browser} onRecheck={() => void checkBrowser()} />
        </div>
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
                  {item.shortfall && (
                    <p
                      className="mt-1 text-xs font-medium text-rose-300"
                      data-testid={`shortfall-${item.id}`}
                    >
                      ⚠ {item.shortfall.message}
                    </p>
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
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <button
                type="button"
                disabled={busy || browser?.reachable === false}
                onClick={() => void fillBasket()}
                className="rounded-full bg-brand-accent px-5 py-2 text-sm font-medium text-brand-dark transition disabled:opacity-40"
              >
                {busy ? 'Filling…' : `Add ${basket.lines.length} lines to the basket`}
              </button>
              <p className="text-xs text-white/50">
                Then add your own extras and pay on nemlig.com.
              </p>
            </div>
          )}
          <BrowserNotice status={browser} onRecheck={() => void checkBrowser()} />

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

          {/* Lines nobody asked for: your own extras, or a surprise. Either
              way, better named than silently ignored. */}
          {reconciliation && reconciliation.unexpected && reconciliation.unexpected.length > 0 && (
            <div className="mt-3 rounded-xl border border-white/15 bg-brand-dark/50 p-3 text-xs text-white/70">
              <p className="font-medium text-white/90">Also in the basket, not from this list:</p>
              <ul className="mt-1 space-y-0.5">
                {reconciliation.unexpected.map((line) => (
                  <li key={`u${line.product_id}`}>
                    {line.name} × {line.qty}
                    {line.price ? ` · ${money(line.price)}` : ''}
                  </li>
                ))}
              </ul>
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
