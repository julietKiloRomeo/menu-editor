import { useRef, useState } from 'react'
import { safariPrintPage } from './print'

/** HTTP home-screen apps cannot use Web Share and cannot safely open a PDF. */
export default function SafariPrintInstructions({ pdfUrl }: { pdfUrl: string }) {
  const input = useRef<HTMLInputElement>(null)
  const [message, setMessage] = useState('')
  const address = safariPrintPage(pdfUrl)

  const copy = async () => {
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(address)
        setMessage('Copied. Open Safari, paste the address, then tap Print menu.')
        return
      } catch {
        // Continue with the older copy command where available.
      }
    }
    input.current?.focus()
    input.current?.select()
    input.current?.setSelectionRange(0, address.length)
    try {
      if (document.execCommand('copy')) {
        setMessage('Copied. Open Safari, paste the address, then tap Print menu.')
        return
      }
    } catch {
      // Some browsers do not expose execCommand.
    }
    setMessage('Select and copy the address below, then paste it into Safari.')
  }

  return (
    <div className="mt-3 text-sm text-white/70">
      <p>To print, copy this address, open Safari and paste it there. Then tap Print menu.</p>
      <input
        ref={input}
        aria-label="Safari print page address"
        readOnly
        value={address}
        onFocus={(event) => event.currentTarget.select()}
        className="mt-2 w-full rounded-lg border border-white/15 bg-brand-dark/40 px-3 py-2 text-xs text-white"
      />
      <button type="button" onClick={() => void copy()} className="mt-2 rounded-full bg-brand-accent px-5 py-2.5 text-sm font-semibold text-brand-dark">
        Copy print address
      </button>
      {message && <p role="status" className="mt-2">{message}</p>}
    </div>
  )
}
