import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import App from '../App'

test('home-screen iPhone opens the current run as a printable PDF', async () => {
  Object.defineProperty(navigator, 'userAgent', { configurable: true, value: 'iPhone' })
  Object.defineProperty(navigator, 'standalone', { configurable: true, value: true })
  window.localStorage.clear()
  window.print = jest.fn()
  global.fetch = jest.fn(async (input) => {
    const url = String(input)
    let body: object = {}
    if (url.endsWith('/api/runs')) body = { runs: [{ id: 13, menu: 'uge_47_2026(1)', total: 63, checked: 29 }] }
    if (url.endsWith('/api/menus')) body = { menus: [] }
    if (url.endsWith('/api/runs/13/render')) body = { markdown: '# Menu\n## Grøn Gnocchi', reconstructed: true }
    return { ok: true, status: 200, headers: { get: () => 'application/json' }, json: async () => body } as Response
  }) as jest.Mock

  render(<MemoryRouter initialEntries={['/run']}><App /></MemoryRouter>)
  fireEvent.click(await screen.findByRole('button', { name: 'Print uge_47_2026(1)' }))

  const printLink = await screen.findByRole('link', { name: '🖨 Print' })
  expect(printLink).toHaveAttribute('href', '/api/runs/13/print.pdf')
  expect(printLink).toHaveAttribute('target', '_blank')
  expect(screen.getByText(/tap Share → Print/i)).toBeInTheDocument()
  expect(window.print).not.toHaveBeenCalled()
})
