import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import App from '../App'

test('home-screen iPhone can copy the current run address without opening a PDF', async () => {
  Object.defineProperty(navigator, 'userAgent', { configurable: true, value: 'iPhone' })
  Object.defineProperty(navigator, 'standalone', { configurable: true, value: true })
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined })
  document.execCommand = jest.fn().mockReturnValue(true)
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

  const copyButton = await screen.findByRole('button', { name: 'Copy print address' })
  expect(screen.getByLabelText('Safari print page address')).toHaveValue('http://localhost/api/runs/13/print')
  fireEvent.click(copyButton)
  expect(document.execCommand).toHaveBeenCalledWith('copy')
  expect(screen.getByRole('status')).toHaveTextContent('Copied. Open Safari')
  expect(screen.queryByRole('link', { name: /Safari to print/i })).not.toBeInTheDocument()
  expect(window.print).not.toHaveBeenCalled()
})

test('copy failure leaves a selectable address and clear instructions', async () => {
  const SafariPrintInstructions = (await import('../SafariPrintInstructions')).default
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined })
  document.execCommand = jest.fn().mockReturnValue(false)
  render(<SafariPrintInstructions pdfUrl="/api/runs/13/print.pdf" />)
  fireEvent.click(screen.getByRole('button', { name: 'Copy print address' }))
  expect(screen.getByRole('status')).toHaveTextContent('Select and copy the address')
  expect(screen.getByLabelText('Safari print page address')).toHaveFocus()
})
