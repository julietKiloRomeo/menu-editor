import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import App from '../../src/App'

function mockStream(options?: {
  supportContinuous?: boolean
  withFocusDistance?: boolean
}) {
  const caps: any = {}
  if (options?.supportContinuous) caps.focusMode = ['continuous']
  if (options?.withFocusDistance) caps.focusDistance = { min: 0, max: 10 }
  const applyConstraints = jest.fn().mockResolvedValue(undefined)
  const track: any = {
    getCapabilities: jest.fn(() => caps),
    applyConstraints,
  }
  return {
    stream: {
      getVideoTracks: () => [track],
    } as any as MediaStream,
    track,
  }
}

beforeEach(() => {
  ;(global.fetch as any) = jest.fn()
  ;(navigator as any).mediaDevices = {
    getUserMedia: jest.fn(),
  }
})

test('starts camera and shows full-screen modal', async () => {
  const { stream, track } = mockStream({ supportContinuous: true })
  ;(navigator.mediaDevices.getUserMedia as any).mockResolvedValue(stream)

  render(
    <MemoryRouter initialEntries={['/add']}>
      <App />
    </MemoryRouter>,
  )

  const startBtn = await screen.findByRole('button', { name: /start camera/i })
  fireEvent.click(startBtn)

  expect(await screen.findByTestId('camera-modal')).toBeInTheDocument()
  // autofocus attempt
  await waitFor(() => {
    expect(track.applyConstraints).toHaveBeenCalled()
  })
})

test('capture triggers parse and populates form', async () => {
  const { stream } = mockStream({ supportContinuous: false })
  ;(navigator.mediaDevices.getUserMedia as any).mockResolvedValue(stream)
  ;(global.fetch as any).mockResolvedValue({
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: async () => ({
      recipe: {
        navn: 'Test Recipe',
        placering: 'Book 12',
        antal: 2,
        ingredienser: { Flour: { amount: 200, unit: 'g' } },
        extras: { Salad: { amount: 1, unit: '' } },
        raw_yaml: 'name: Test Recipe',
      },
    }),
  })

  render(
    <MemoryRouter initialEntries={['/add']}>
      <App />
    </MemoryRouter>,
  )

  fireEvent.click(await screen.findByRole('button', { name: /start camera/i }))
  fireEvent.click(await screen.findByRole('button', { name: /capture photo/i }))

  // Name field should be populated after parsing
  await waitFor(async () => {
    const nameInput = await screen.findByPlaceholderText(/recipe title/i)
    expect(nameInput).toHaveValue('Test Recipe')
  })
})

test('shows spinner overlay while processing', async () => {
  const { stream } = mockStream()
  ;(navigator.mediaDevices.getUserMedia as any).mockResolvedValue(stream)
  ;(global.fetch as any).mockResolvedValue({
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: async () => ({ recipe: { navn: 'Spin Test', ingredienser: {}, extras: {} } }),
  })

  render(
    <MemoryRouter initialEntries={['/add']}>
      <App />
    </MemoryRouter>,
  )

  fireEvent.click(await screen.findByRole('button', { name: /start camera/i }))
  fireEvent.click(await screen.findByRole('button', { name: /capture photo/i }))

  // Spinner overlay should appear during processing
  expect(await screen.findByTestId('processing-overlay')).toBeInTheDocument()
})

test('manual focus slider applies constraints when supported', async () => {
  const { stream, track } = mockStream({ withFocusDistance: true })
  ;(navigator.mediaDevices.getUserMedia as any).mockResolvedValue(stream)

  render(
    <MemoryRouter initialEntries={['/add']}>
      <App />
    </MemoryRouter>,
  )

  fireEvent.click(await screen.findByRole('button', { name: /start camera/i }))

  const slider = await screen.findByRole('slider', { name: /focus/i })
  fireEvent.change(slider, { target: { value: '5' } })

  await waitFor(() => {
    expect(track.applyConstraints).toHaveBeenCalledWith({ advanced: [{ focusMode: 'manual', focusDistance: 5 }] })
  })
})

test('preserves ingredient order from parser', async () => {
  const { stream } = mockStream()
  ;(navigator.mediaDevices.getUserMedia as any).mockResolvedValue(stream)
  ;(global.fetch as any).mockResolvedValue({
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: async () => ({
      recipe: {
        navn: 'Ordered',
        placering: '',
        antal: 1,
        ingredienser: { First: { amount: 1, unit: 'stk' }, Second: { amount: 2, unit: 'stk' } },
        extras: {},
      },
    }),
  })

  render(
    <MemoryRouter initialEntries={['/add']}>
      <App />
    </MemoryRouter>,
  )

  fireEvent.click(await screen.findByRole('button', { name: /start camera/i }))
  fireEvent.click(await screen.findByRole('button', { name: /capture photo/i }))

  const inputs = await screen.findAllByPlaceholderText(/ingredient/i)
  expect(inputs[0]).toHaveValue('First')
  expect(inputs[1]).toHaveValue('Second')
})

test('adding a new row prepends to top', async () => {
  render(
    <MemoryRouter initialEntries={['/add']}>
      <App />
    </MemoryRouter>,
  )

  // Type into the initial row to differentiate it
  let inputs = await screen.findAllByPlaceholderText(/ingredient/i)
  fireEvent.change(inputs[0], { target: { value: 'Existing' } })

  // Add new row
  const addBtn = await screen.findByRole('button', { name: /add row/i })
  fireEvent.click(addBtn)

  inputs = await screen.findAllByPlaceholderText(/ingredient/i)
  expect(inputs[0]).toHaveValue('')
  expect(inputs[1]).toHaveValue('Existing')
})
