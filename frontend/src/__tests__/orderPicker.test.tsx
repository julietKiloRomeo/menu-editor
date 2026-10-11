import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import OrderPicker from '../OrderPicker'


const candidate = {
  product_id: '111',
  name: 'Letmælk',
  pack: '1 l',
  price: 12,
  image: 'https://img/milk.jpg',
  unit_price: '12 kr/l',
  fav: true,
  previous: true,
  from_memory: false,
}

const item = {
  id: 10,
  ingredient: 'mælk',
  need: '5 dl',
  recipes: ['Pandekager'],
  zone: 'køl',
  status: 'mapped' as const,
  query: 'letmælk',
  candidates: [candidate],
  warning: '',
  action: 'buy' as const,
  product_id: '111',
  product: candidate,
  qty: 1,
  qty_manual: false,
  note: '',
  url: '',
  shortfall: null,
}

const order = {
  id: 9,
  run_id: 3,
  source: 'uge_42_2026',
  created_at: '2026-10-10T08:00:00Z',
  recorded_at: null,
  decided: 1,
  total: 1,
  items: [item],
  collisions: [],
  shortfalls: [],
}

const basket = {
  lines: [{ product_id: '111', product_name: 'Letmælk', pack: '1 l', price: 12, qty: 1, covers: ['mælk'], zone: 'køl' }],
  merged: [],
  unresolved: [],
  declined: 0,
}

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

beforeEach(() => {
  window.history.replaceState({}, '', '/order')
})

test('one click starts the latest run and searches live products', async () => {
  const fetchMock = jest.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/api/orders') && !init?.method) return response({ orders: [] })
    if (url.endsWith('/api/runs')) return response({ runs: [{ id: 3, menu: 'uge_42_2026', created_at: order.created_at, checked: 18, total: 54 }] })
    if (url.endsWith('/api/browser/status')) return response({ reachable: true, tab: 'https://www.nemlig.com/', detail: '' })
    if (url.endsWith('/api/orders/latest')) return response({ ...order, resumed: false, decided: 0, items: [{ ...item, action: null, product_id: null, product: null, candidates: [] }] }, 201)
    if (url.endsWith('/api/orders/9/run-search')) return response({ searched: 1, without_candidates: [], order })
    if (url.endsWith('/api/orders/9/basket')) return response(basket)
    throw new Error(`Unexpected request: ${init?.method || 'GET'} ${url}`)
  })
  global.fetch = fetchMock

  render(<OrderPicker apiBase="" pushToast={jest.fn()} />)
  const start = await screen.findByRole('button', { name: /start latest & search/i })
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/browser/status', expect.anything()))
  fireEvent.click(start)

  expect(await screen.findByText('Letmælk')).toBeInTheDocument()
  expect(fetchMock).toHaveBeenCalledWith(
    '/api/orders/9/run-search',
    expect.objectContaining({ method: 'POST' }),
  )
})

test('a clean basket fill records the order automatically', async () => {
  window.history.replaceState({}, '', '/order?order=9')
  const fetchMock = jest.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/api/orders') && !init?.method) return response({ orders: [order] })
    if (url.endsWith('/api/runs')) return response({ runs: [] })
    if (url.endsWith('/api/browser/status')) return response({ reachable: true, tab: 'https://www.nemlig.com/', detail: '' })
    if (url.endsWith('/api/orders/9') && !init?.method) return response(order)
    if (url.endsWith('/api/orders/9/basket')) return response(basket)
    if (url.endsWith('/api/orders/9/fill-basket')) {
      return response({
        failed: [],
        reconciliation: { ok: true, sold_out: [], missing: [], mismatched: [], unexpected: [], total: 12, product_count: 1 },
      })
    }
    if (url.endsWith('/api/orders/9/record')) return response({ added: 0, updated: 1 })
    throw new Error(`Unexpected request: ${init?.method || 'GET'} ${url}`)
  })
  global.fetch = fetchMock

  render(<OrderPicker apiBase="" pushToast={jest.fn()} />)
  const fill = await screen.findByRole('button', { name: /fill basket & remember/i })
  fireEvent.click(fill)

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/orders/9/record',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
