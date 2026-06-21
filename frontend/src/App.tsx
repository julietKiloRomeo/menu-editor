import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent, DragEvent, FormEvent } from 'react'
import { marked } from 'marked'
import html2pdf from 'html2pdf.js'
import { useLocation, useNavigate } from 'react-router-dom'

const API_BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '')
const RECIPES_ENDPOINT = `${API_BASE}/api/recipes?include_blacklisted=0`

type IngredientBucket = {
  amount: number
  unit: string
}

type Recipe = {
  id: number
  slug: string
  navn: string
  placering?: string | null
  antal: number
  ingredienser: Record<string, IngredientBucket>
  extras: Record<string, IngredientBucket>
  is_blacklisted: boolean
  is_whitelisted: boolean
}

type SelectionEntry = {
  recipe: Recipe
  servings: number
}

type SelectionState = Record<string, SelectionEntry>

type ToastKind = 'success' | 'error' | 'info'

type Toast = {
  id: number
  kind: ToastKind
  message: string
}

type View = 'planner' | 'add' | 'edit' | 'shopping' | 'tools' | 'config'

type MenuPreview = {
  menuHtml: string
  shoppingHtml: string
}

type IngredientFormRow = {
  id: string
  navn: string
  amount: string
  unit: string
}

const createRow = (overrides?: Partial<IngredientFormRow>): IngredientFormRow => ({
  id: typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`,
  navn: '',
  amount: '',
  unit: '',
  ...overrides,
})

const parseAmountInput = (value: string): number => {
  const cleaned = value.replace(',', '.').trim()
  if (!cleaned) return NaN
  const parsed = Number.parseFloat(cleaned)
  return Number.isFinite(parsed) ? parsed : NaN
}

const ensureJson = async <T,>(response: Response): Promise<T> => {
  const contentType = response.headers.get('content-type') || ''
  if (!contentType.includes('application/json')) {
    const bodySnippet = (await response.text()).slice(0, 200)
    throw new Error(`Unexpected response (status ${response.status}): ${bodySnippet}`)
  }
  return response.json() as Promise<T>
}

function App() {
  const [recipes, setRecipes] = useState<Recipe[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [selection, setSelection] = useState<SelectionState>(() => {
    if (typeof window === 'undefined') return {}
    try {
      const raw = window.localStorage.getItem('menu-spinner.selection.v1')
      if (!raw) return {}
      const parsed = JSON.parse(raw)
      return (parsed && typeof parsed === 'object') ? (parsed as SelectionState) : {}
    } catch {
      return {}
    }
  })
  const [spinnerResults, setSpinnerResults] = useState<Recipe[]>([])
  const [menuMarkdown, setMenuMarkdown] = useState<string>('')
  const [menuPreview, setMenuPreview] = useState<MenuPreview | null>(null)
  const [exporting, setExporting] = useState(false)
  const [formName, setFormName] = useState('')
  const [formPlacement, setFormPlacement] = useState('')
  const [formServings, setFormServings] = useState(4)
  const [ingredientRows, setIngredientRows] = useState<IngredientFormRow[]>([createRow()])
  const [extraRows, setExtraRows] = useState<IngredientFormRow[]>([])
  const [imagePrompt, setImagePrompt] = useState('')
  const [imagePreviewUrl, setImagePreviewUrl] = useState<string | null>(null)
  const [imageFilename, setImageFilename] = useState<string | null>(null)
  const [imageProcessing, setImageProcessing] = useState(false)
  const [focusSupported, setFocusSupported] = useState(false)
  const [focusMin, setFocusMin] = useState<number | null>(null)
  const [focusMax, setFocusMax] = useState<number | null>(null)
  const [focusValue, setFocusValue] = useState<number | null>(null)
  const videoTrackRef = useRef<MediaStreamTrack | null>(null)
  const [generatedYaml, setGeneratedYaml] = useState('')
  const [cameraActive, setCameraActive] = useState(false)
  const [addInputMode, setAddInputMode] = useState<'photo' | 'camera' | 'manual'>('photo')
  const [renameFrom, setRenameFrom] = useState('')
  const [renameTo, setRenameTo] = useState('')
  const [renameIncludeExtras, setRenameIncludeExtras] = useState(true)
  const [renameCaseInsensitive, setRenameCaseInsensitive] = useState(true)
  const [renameForce, setRenameForce] = useState(false)
  const [renameSubmitting, setRenameSubmitting] = useState(false)
  const [renameResult, setRenameResult] = useState<string | null>(null)
  const [renameConflicts, setRenameConflicts] = useState<string | null>(null)
  const [renameCandidate, setRenameCandidate] = useState('')

  const [configLoading, setConfigLoading] = useState(false)
  const [configCategories, setConfigCategories] = useState<Array<{ id: number; name: string; priority: number }>>([])
  const [configItems, setConfigItems] = useState<Array<{ id: number; name: string; category_id: number | null; category_name?: string | null }>>([])
  const [configStaples, setConfigStaples] = useState<Array<{ id: number; name: string; amount: number; unit: string }>>([])
  const [configStapleLabel, setConfigStapleLabel] = useState('')
  const [configStapleOptions, setConfigStapleOptions] = useState<string[]>([])
  const [configStatus, setConfigStatus] = useState<string | null>(null)
  const [configLoaded, setConfigLoaded] = useState(false)
  const [newCategoryName, setNewCategoryName] = useState('')
  const [customStapleLabel, setCustomStapleLabel] = useState('')
  const [newCategoryPriority, setNewCategoryPriority] = useState('0')
  const [newIngredientName, setNewIngredientName] = useState('')
  const [newIngredientCategory, setNewIngredientCategory] = useState<number | ''>('')
  const [newStapleName, setNewStapleName] = useState('')
  const [newStapleAmount, setNewStapleAmount] = useState('1')
  const [newStapleUnit, setNewStapleUnit] = useState('stk')

  const [editSearch, setEditSearch] = useState('')
  const [editSlug, setEditSlug] = useState<string | null>(null)
  const [editSlugInput, setEditSlugInput] = useState('')
  const [editName, setEditName] = useState('')
  const [editPlacement, setEditPlacement] = useState('')
  const [editServings, setEditServings] = useState(4)
  const [editIngredients, setEditIngredients] = useState<IngredientFormRow[]>([createRow()])
  const [editExtras, setEditExtras] = useState<IngredientFormRow[]>([])
  const [editIsBlacklisted, setEditIsBlacklisted] = useState(false)
  const [editIsWhitelisted, setEditIsWhitelisted] = useState(false)
  const [editStatus, setEditStatus] = useState<string | null>(null)
  const DRAG_MIME = 'application/x-recipe-row'
  const [toasts, setToasts] = useState<Toast[]>([])
  const toastTimeouts = useRef<number[]>([])
  const pdfPreviewRef = useRef<HTMLDivElement | null>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const mediaStreamRef = useRef<MediaStream | null>(null)
  const [dropActive, setDropActive] = useState(false)

  const location = useLocation()
  const navigate = useNavigate()

  const view: View = useMemo(() => {
    switch (location.pathname) {
      case '/add':
        return 'add'
      case '/edit':
        return 'edit'
      case '/config':
        return 'config'
      case '/shopping':
        return 'shopping'
      case '/tools':
        return 'tools'
      default:
        return 'planner'
    }
  }, [location.pathname])

  const goToView = useCallback((next: View) => {
    switch (next) {
      case 'planner':
        navigate('/')
        break
      case 'add':
        navigate('/add')
        break
      case 'edit':
        navigate('/edit')
        break
      case 'config':
        navigate('/config')
        break
      case 'shopping':
        navigate('/shopping')
        break
      case 'tools':
        navigate('/tools')
        break
    }
  }, [navigate])

  const stopCamera = useCallback(() => {
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop())
      mediaStreamRef.current = null
    }
    setCameraActive(false)
    videoTrackRef.current = null
    setFocusSupported(false)
    setFocusMin(null)
    setFocusMax(null)
    setFocusValue(null)
  }, [])

  const ingredientNames = useMemo(() => {
    const names = new Set<string>()
    editIngredients.forEach((row) => {
      const name = row.navn.trim()
      if (name) names.add(name)
    })
    editExtras.forEach((row) => {
      const name = row.navn.trim()
      if (name) names.add(name)
    })
    return Array.from(names).sort((a, b) => a.localeCompare(b))
  }, [editIngredients, editExtras])

  useEffect(() => {
    if (view !== 'edit') {
      return
    }
    if (!renameCandidate || !ingredientNames.includes(renameCandidate)) {
      setRenameCandidate(ingredientNames[0] ?? '')
    }
  }, [ingredientNames, renameCandidate, view])

    const pushToast = useCallback((kind: ToastKind, message: string) => {
    const id = Date.now() + Math.floor(Math.random() * 1000)
    setToasts((prev) => [...prev, { id, kind, message }])
    const timeout = window.setTimeout(() => {
      setToasts((prev) => prev.filter((toast) => toast.id !== id))
    }, 4000)
    toastTimeouts.current.push(timeout)
  }, [])

  useEffect(() => {
    return () => {
      toastTimeouts.current.forEach((timeout) => window.clearTimeout(timeout))
      if (imagePreviewUrl) {
        URL.revokeObjectURL(imagePreviewUrl)
      }
      stopCamera()
    }
  }, [imagePreviewUrl, stopCamera])

  const loadRecipes = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(RECIPES_ENDPOINT)
      const payload = await ensureJson<{ recipes?: Recipe[]; error?: string }>(response)
      if (!response.ok) {
        const message = payload.error ?? `Server responded with ${response.status}`
        throw new Error(message)
      }
      const normalised: Recipe[] = (payload.recipes ?? []).map((recipe: Recipe) => ({
        ...recipe,
        placering: recipe.placering ?? '',
        ingredienser: recipe.ingredienser ?? {},
        extras: recipe.extras ?? {},
      }))
      setRecipes(normalised)
    } catch (err) {
      setError((err as Error).message)
      setRecipes([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadRecipes()
  }, [loadRecipes])

  // Persist selection across reloads so the user doesn't lose their menu on refresh.
  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem('menu-spinner.selection.v1', JSON.stringify(selection))
    } catch {
      /* localStorage full or unavailable; ignore */
    }
  }, [selection])

  // Rebind persisted selection against the freshly-loaded recipes (so we use the
  // latest recipe data rather than the snapshot saved at the time it was added),
  // and drop selections whose recipe no longer exists.
  useEffect(() => {
    if (!recipes.length) return
    setSelection((prev) => {
      const next: SelectionState = {}
      let changed = false
      for (const slug of Object.keys(prev)) {
        const live = recipes.find((r) => r.slug === slug)
        if (!live) {
          changed = true
          continue
        }
        const servings = prev[slug].servings
        if (prev[slug].recipe !== live) {
          changed = true
          next[slug] = { recipe: live, servings }
        } else {
          next[slug] = prev[slug]
        }
      }
      return changed ? next : prev
    })
  }, [recipes])

  useEffect(() => {
    if (view !== 'add') {
      stopCamera()
    }
  }, [stopCamera, view])

  useEffect(() => {
    // Ensure the video element attaches to the active stream even if mounted later
    if (cameraActive && videoRef.current && mediaStreamRef.current) {
      try {
        videoRef.current.srcObject = mediaStreamRef.current
        // eslint-disable-next-line @typescript-eslint/no-floating-promises
        videoRef.current.play()
      } catch {
        /* ignore */
      }
    }
  }, [cameraActive])

  const resetForm = useCallback(() => {
    setFormName('')
    setFormPlacement('')
    setFormServings(4)
    setIngredientRows([createRow()])
    setExtraRows([])
    setImagePrompt('')
    if (imagePreviewUrl) {
      URL.revokeObjectURL(imagePreviewUrl)
    }
    setImagePreviewUrl(null)
    setImageFilename(null)
    setGeneratedYaml('')
    setImageProcessing(false)
    stopCamera()
    setMenuPreview(null)
    setMenuMarkdown('')
    setDropActive(false)
  }, [imagePreviewUrl, stopCamera])

  const ensureAtLeastOneIngredientRow = useCallback((rows: IngredientFormRow[]) => (
    rows.length > 0 ? rows : [createRow()]
  ), [])

  const updateIngredientRow = useCallback((id: string, updates: Partial<IngredientFormRow>) => {
    setIngredientRows((prev) => ensureAtLeastOneIngredientRow(prev.map((row) => (row.id === id ? { ...row, ...updates } : row))))
  }, [ensureAtLeastOneIngredientRow])

  const updateExtraRow = useCallback((id: string, updates: Partial<IngredientFormRow>) => {
    setExtraRows((prev) => prev.map((row) => (row.id === id ? { ...row, ...updates } : row)))
  }, [])

  const removeIngredientRow = useCallback((id: string) => {
    setIngredientRows((prev) => ensureAtLeastOneIngredientRow(prev.filter((row) => row.id !== id)))
  }, [ensureAtLeastOneIngredientRow])

  const removeExtraRow = useCallback((id: string) => {
    setExtraRows((prev) => prev.filter((row) => row.id !== id))
  }, [])

  const addIngredientRow = useCallback(() => {
    setIngredientRows((prev) => [createRow(), ...prev])
  }, [])

  const addExtraRow = useCallback(() => {
    setExtraRows((prev) => [createRow({ unit: '', amount: '1' }), ...prev])
  }, [])

  const updateEditIngredientRow = useCallback((id: string, updates: Partial<IngredientFormRow>) => {
    setEditIngredients((prev) => ensureAtLeastOneIngredientRow(prev.map((row) => (row.id === id ? { ...row, ...updates } : row))))
  }, [ensureAtLeastOneIngredientRow])

  const updateEditExtraRow = useCallback((id: string, updates: Partial<IngredientFormRow>) => {
    setEditExtras((prev) => prev.map((row) => (row.id === id ? { ...row, ...updates } : row)))
  }, [])

  const addEditIngredientRow = useCallback(() => {
    setEditIngredients((prev) => [createRow(), ...prev])
  }, [])

  const addEditExtraRow = useCallback(() => {
    setEditExtras((prev) => [createRow({ unit: '', amount: '1' }), ...prev])
  }, [])

  const removeEditIngredientRow = useCallback((id: string) => {
    setEditIngredients((prev) => ensureAtLeastOneIngredientRow(prev.filter((row) => row.id !== id)))
  }, [ensureAtLeastOneIngredientRow])

  const removeEditExtraRow = useCallback((id: string) => {
    setEditExtras((prev) => prev.filter((row) => row.id !== id))
  }, [])

  const populateEditForm = useCallback((recipe: Recipe | null) => {
    if (!recipe) {
      setEditSlug(null)
      setEditSlugInput('')
      setEditName('')
      setEditPlacement('')
      setEditServings(4)
      setEditIsBlacklisted(false)
      setEditIsWhitelisted(false)
      setEditIngredients([createRow()])
      setEditExtras([])
      setRenameCandidate('')
      setEditStatus(null)
      return
    }
    setEditSlug(recipe.slug)
    setEditSlugInput(recipe.slug)
    setEditName(recipe.navn)
    setEditPlacement(recipe.placering ?? '')
    setEditServings(recipe.antal ?? 4)
    setEditIsBlacklisted(Boolean(recipe.is_blacklisted))
    setEditIsWhitelisted(Boolean(recipe.is_whitelisted))
    const ingredientEntries = Object.entries(recipe.ingredienser ?? {}) as Array<[string, IngredientBucket]>
    setEditIngredients(ensureAtLeastOneIngredientRow(
      ingredientEntries.length
        ? ingredientEntries.map(([name, bucket]) =>
            createRow({ navn: name, amount: bucket?.amount != null ? String(bucket.amount) : '', unit: bucket?.unit ?? '' }))
        : [createRow()]
    ))
    const extrasEntries = Object.entries(recipe.extras ?? {}) as Array<[string, IngredientBucket]>
    setEditExtras(
      extrasEntries.map(([name, bucket]) =>
        createRow({ navn: name, amount: bucket?.amount != null ? String(bucket.amount) : '1', unit: bucket?.unit ?? '' })
      )
    )
    const firstIngredient = ingredientEntries[0]?.[0] ?? extrasEntries[0]?.[0] ?? ''
    setRenameCandidate(firstIngredient)
    setEditStatus(null)
  }, [ensureAtLeastOneIngredientRow])

  const handleEditSelect = useCallback((slug: string) => {
    const recipe = recipes.find((candidate) => candidate.slug === slug)
    if (!recipe) {
      return
    }
    populateEditForm(recipe)
  }, [populateEditForm, recipes])

  const handleEditReset = useCallback(() => {
    if (editSlug) {
      const recipe = recipes.find((candidate) => candidate.slug === editSlug)
      populateEditForm(recipe ?? null)
    } else {
      populateEditForm(null)
    }
  }, [editSlug, populateEditForm, recipes])

  const openRenameTools = useCallback((name?: string) => {
    const source = (name ?? renameCandidate ?? '').trim()
    if (!source) {
      pushToast('info', 'Enter or select an ingredient name first.')
      return
    }
    setRenameFrom(source)
    setRenameTo('')
    setRenameConflicts(null)
    setRenameResult(null)
    goToView('tools')
  }, [goToView, pushToast, renameCandidate])

  const moveIngredientToExtras = useCallback((rowId: string) => {
    setEditIngredients((prev) => {
      const idx = prev.findIndex((r) => r.id === rowId)
      if (idx === -1) return ensureAtLeastOneIngredientRow(prev)
      const row = prev[idx]
      const remaining = prev.filter((r) => r.id !== rowId)
      setEditExtras((extraPrev) => [...extraPrev, row])
      return ensureAtLeastOneIngredientRow(remaining)
    })
  }, [ensureAtLeastOneIngredientRow])

  const moveExtraToIngredients = useCallback((rowId: string) => {
    setEditExtras((prev) => {
      const idx = prev.findIndex((r) => r.id === rowId)
      if (idx === -1) return prev
      const row = prev[idx]
      const remaining = prev.filter((r) => r.id !== rowId)
      setEditIngredients((ingPrev) => ensureAtLeastOneIngredientRow([...ingPrev, row]))
      return remaining
    })
  }, [ensureAtLeastOneIngredientRow])

  const onDropToIngredients = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    try {
      const json = event.dataTransfer.getData(DRAG_MIME)
      const payload = JSON.parse(json) as { id: string; source: 'ingredients' | 'extras' }
      if (payload?.id && payload.source === 'extras') {
        moveExtraToIngredients(payload.id)
      }
    } catch {
      /* ignore */
    }
  }, [moveExtraToIngredients])

  const onDropToExtras = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    try {
      const json = event.dataTransfer.getData(DRAG_MIME)
      const payload = JSON.parse(json) as { id: string; source: 'ingredients' | 'extras' }
      if (payload?.id && payload.source === 'ingredients') {
        moveIngredientToExtras(payload.id)
      }
    } catch {
      /* ignore */
    }
  }, [moveIngredientToExtras])

  const allowDrop = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }, [])

  const slugFromName = useCallback(() => {
    const base = editName.trim().toLowerCase()
    if (!base) {
      pushToast('info', 'Set a recipe name before generating a slug.')
      return
    }
    const slug = base
      .normalize('NFKD')
      .replace(/[^a-z0-9\s-]/g, '')
      .trim()
      .replace(/\s+/g, '-')
      .replace(/-+/g, '-')
    setEditSlugInput(slug)
  }, [editName, pushToast])

  const processImage = useCallback(
    async (file: File) => {
      setImageProcessing(true)
      try {
        const formData = new FormData()
        formData.append('image', file)
        if (imagePrompt.trim()) {
          formData.append('prompt', imagePrompt.trim())
        }
        const response = await fetch(`${API_BASE}/api/recipes/from-image`, {
          method: 'POST',
          body: formData,
        })
        const payload = await ensureJson<{ recipe?: any; error?: string }>(response)
        if (!response.ok) {
          const message = payload.error ?? `Image parsing failed (${response.status})`
          throw new Error(message)
        }
        const recipe = payload.recipe ?? {}
        setFormName(recipe.navn ?? '')
        setFormPlacement(recipe.placering ?? '')
        setFormServings(typeof recipe.antal === 'number' && recipe.antal >= 0 ? recipe.antal : 4)
        const ingredientEntries = Object.entries(recipe.ingredienser ?? {}) as Array<[string, IngredientBucket]>
        setIngredientRows(ensureAtLeastOneIngredientRow(
          ingredientEntries.length
            ? ingredientEntries.map(([name, bucket]: [string, IngredientBucket]) =>
                createRow({ navn: name, amount: bucket?.amount != null ? String(bucket.amount) : '', unit: bucket?.unit ?? '' }))
            : [createRow()]
        ))
        const extraEntries = Object.entries(recipe.extras ?? {}) as Array<[string, IngredientBucket]>
        setExtraRows(
          extraEntries.map(([name, bucket]: [string, IngredientBucket]) =>
            createRow({ navn: name, amount: bucket?.amount != null ? String(bucket.amount) : '1', unit: bucket?.unit ?? '' })
          ),
        )
        setGeneratedYaml(recipe.raw_yaml ?? '')
        pushToast('success', 'Recipe draft generated. Review the fields before saving.')
        goToView('add')
      } catch (err) {
        pushToast('error', (err as Error).message)
      } finally {
        setImageProcessing(false)
      }
    },
    [imagePrompt, ensureAtLeastOneIngredientRow, pushToast],
  )

  const handleFileSelection = useCallback(
    async (file: File | null) => {
      if (!file) {
        return
      }
      if (!file.type.startsWith('image/')) {
        pushToast('error', 'Please choose an image file.')
        return
      }
      if (imagePreviewUrl) {
        URL.revokeObjectURL(imagePreviewUrl)
      }
      const url = URL.createObjectURL(file)
      setImagePreviewUrl(url)
      setImageFilename(file.name || 'recipe-photo.jpg')
      setGeneratedYaml('')
      await processImage(file)
    },
    [imagePreviewUrl, processImage, pushToast],
  )

  const handlePromptChange = useCallback((event: ChangeEvent<HTMLTextAreaElement>) => {
    setImagePrompt(event.target.value)
  }, [])

  const onDrop = useCallback(
    async (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault()
      event.stopPropagation()
      const file = event.dataTransfer?.files?.[0]
      setDropActive(false)
      if (file) {
        await handleFileSelection(file)
      }
    },
    [handleFileSelection],
  )

  const onDragEnter = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    setDropActive(true)
  }, [])

  const onDragLeave = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    setDropActive(false)
  }, [])

  const onDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
  }, [])

  const onFileInputChange = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0] ?? null
      await handleFileSelection(file)
    },
    [handleFileSelection],
  )

  const applyConfigPayload = useCallback((payload: {
    categories?: Array<{ id: number; name: string; priority: number }>
    items?: Array<{ id: number; name: string; category_id: number | null; category_name?: string | null }>
    staples?: Array<{ id: number; name: string; amount: number; unit: string }>
    staple_label?: string
    staple_label_options?: string[]
  }) => {
    const categories = (payload.categories ?? []).map((category) => ({
      id: category.id,
      name: category.name ?? '',
      priority: category.priority ?? 0,
    }))
    setConfigCategories(categories)
    setConfigItems((payload.items ?? []).map((item) => ({
      id: item.id,
      name: item.name ?? '',
      category_id: item.category_id ?? null,
      category_name: item.category_name ?? null,
    })))
    setConfigStaples((payload.staples ?? []).map((staple) => ({
      id: staple.id,
      name: staple.name ?? '',
      amount: staple.amount ?? 1,
      unit: staple.unit ?? '',
    })))
    setConfigStapleLabel(payload.staple_label ?? '')
    setConfigStapleOptions(payload.staple_label_options ?? [])
    setNewIngredientCategory(categories[0]?.id ?? '')
    setConfigLoaded(true)
  }, [])

  const fetchConfigData = useCallback(async () => {
    setConfigLoading(true)
    try {
      const response = await fetch(`${API_BASE}/api/config`)
      const payload = await ensureJson<{
        categories?: Array<{ id: number; name: string; priority: number }>
        items?: Array<{ id: number; name: string; category_id: number | null; category_name?: string | null }>
        staples?: Array<{ id: number; name: string; amount: number; unit: string }>
        staple_label?: string
        staple_label_options?: string[]
        error?: string
      }>(response)
      if (!response.ok) {
        const message = payload.error ?? `Failed to load config (${response.status})`
        throw new Error(message)
      }
      applyConfigPayload(payload)
      setConfigStatus(null)
    } catch (err) {
      const message = (err as Error).message
      setConfigStatus(message)
      pushToast('error', message)
    } finally {
      setConfigLoading(false)
    }
  }, [applyConfigPayload, pushToast])

  const updateCategoryDraft = useCallback((id: number, updates: Partial<{ name: string; priority: number }>) => {
    setConfigCategories((prev) => prev.map((category) => (category.id === id ? { ...category, ...updates } : category)))
  }, [])

  const updateItemDraft = useCallback((id: number, updates: Partial<{ name: string; category_id: number | null }>) => {
    setConfigItems((prev) => prev.map((item) => (item.id === id ? { ...item, ...updates } : item)))
  }, [])

  const updateStapleDraft = useCallback((id: number, updates: Partial<{ name: string; amount: number; unit: string }>) => {
    setConfigStaples((prev) => prev.map((staple) => (staple.id === id ? { ...staple, ...updates } : staple)))
  }, [])

  const handleConfigSuccess = useCallback((payload: {
    categories?: Array<{ id: number; name: string; priority: number }>
    items?: Array<{ id: number; name: string; category_id: number | null; category_name?: string | null }>
    staples?: Array<{ id: number; name: string; amount: number; unit: string }>
    staple_label?: string
    staple_label_options?: string[]
    error?: string
  }, message: string) => {
    applyConfigPayload(payload)
    setConfigStatus(message)
    pushToast('success', message)
  }, [applyConfigPayload, pushToast])

  const handleConfigFailure = useCallback((error: unknown) => {
    const message = (error as Error).message
    setConfigStatus(message)
    setConfigLoaded(true)
    pushToast('error', message)
  }, [pushToast])

  const postCategory = useCallback(async (url: string, method: 'POST' | 'PATCH', body: unknown, successMessage: string) => {
    try {
      setConfigLoading(true)
      const response = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const payload = await ensureJson<{
        categories?: Array<{ id: number; name: string; priority: number }>
        items?: Array<{ id: number; name: string; category_id: number | null; category_name?: string | null }>
        staples?: Array<{ id: number; name: string; amount: number; unit: string }>
        staple_label?: string
        staple_label_options?: string[]
        error?: string
      }>(response)
      if (!response.ok) {
        const message = payload.error ?? `${successMessage} failed (${response.status})`
        throw new Error(message)
      }
      handleConfigSuccess(payload, successMessage)
    } catch (err) {
      handleConfigFailure(err)
    } finally {
      setConfigLoading(false)
    }
  }, [handleConfigFailure, handleConfigSuccess])

  const handleCategoryCreate = useCallback(async () => {
    if (!newCategoryName.trim()) {
      setConfigStatus('Category name is required.')
      return
    }
    const priority = Number.parseInt(newCategoryPriority, 10) || 0
    await postCategory(`${API_BASE}/api/config/categories`, 'POST', { name: newCategoryName.trim(), priority }, 'Category created.')
    setNewCategoryName('')
    setNewCategoryPriority('0')
  }, [newCategoryName, newCategoryPriority, postCategory])

  const handleCategorySave = useCallback(async (categoryId: number) => {
    const category = configCategories.find((entry) => entry.id === categoryId)
    if (!category) {
      return
    }
    const priority = Number.isFinite(category.priority) ? category.priority : 0
    await postCategory(`${API_BASE}/api/config/categories/${categoryId}`, 'PATCH', { name: category.name.trim(), priority }, 'Category updated.')
  }, [configCategories, postCategory])

  const handleCategoryDelete = useCallback(async (categoryId: number) => {
    try {
      setConfigLoading(true)
      const response = await fetch(`${API_BASE}/api/config/categories/${categoryId}`, { method: 'DELETE' })
      const payload = await ensureJson<{ categories?: any; items?: any; staples?: any; staple_label?: string; staple_label_options?: string[]; error?: string }>(response)
      if (!response.ok) {
        const message = payload.error ?? `Delete failed (${response.status})`
        throw new Error(message)
      }
      handleConfigSuccess(payload, 'Category removed.')
    } catch (err) {
      handleConfigFailure(err)
    } finally {
      setConfigLoading(false)
    }
  }, [handleConfigFailure, handleConfigSuccess])

  const handleIngredientCreate = useCallback(async () => {
    if (!newIngredientName.trim()) {
      setConfigStatus('Ingredient name is required.')
      return
    }
    const categoryId = typeof newIngredientCategory === 'number' ? newIngredientCategory : Number.parseInt(String(newIngredientCategory), 10)
    if (!Number.isInteger(categoryId)) {
      setConfigStatus('Choose a category for the ingredient.')
      return
    }
    try {
      setConfigLoading(true)
      const response = await fetch(`${API_BASE}/api/config/items`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newIngredientName.trim(), category_id: categoryId }),
      })
      const payload = await ensureJson<{ categories?: any; items?: any; staples?: any; staple_label?: string; staple_label_options?: string[]; error?: string }>(response)
      if (!response.ok) {
        const message = payload.error ?? `Failed to add ingredient (${response.status})`
        throw new Error(message)
      }
      handleConfigSuccess(payload, 'Ingredient mapping added.')
      setNewIngredientName('')
    } catch (err) {
      handleConfigFailure(err)
    } finally {
      setConfigLoading(false)
    }
  }, [handleConfigFailure, handleConfigSuccess, newIngredientCategory, newIngredientName])

  const handleIngredientSave = useCallback(async (itemId: number) => {
    const item = configItems.find((entry) => entry.id === itemId)
    if (!item) {
      return
    }
    const categoryId = item.category_id
    if (categoryId == null) {
      setConfigStatus('Select a category before saving the ingredient.')
      return
    }
    try {
      setConfigLoading(true)
      const response = await fetch(`${API_BASE}/api/config/items/${itemId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: item.name.trim(), category_id: categoryId }),
      })
      const payload = await ensureJson<{ categories?: any; items?: any; staples?: any; staple_label?: string; staple_label_options?: string[]; error?: string }>(response)
      if (!response.ok) {
        const message = payload.error ?? `Failed to update ingredient (${response.status})`
        throw new Error(message)
      }
      handleConfigSuccess(payload, 'Ingredient mapping updated.')
    } catch (err) {
      handleConfigFailure(err)
    } finally {
      setConfigLoading(false)
    }
  }, [configItems, handleConfigFailure, handleConfigSuccess])

  const handleIngredientDelete = useCallback(async (itemId: number) => {
    try {
      setConfigLoading(true)
      const response = await fetch(`${API_BASE}/api/config/items/${itemId}`, { method: 'DELETE' })
      const payload = await ensureJson<{ categories?: any; items?: any; staples?: any; staple_label?: string; staple_label_options?: string[]; error?: string }>(response)
      if (!response.ok) {
        const message = payload.error ?? `Failed to delete ingredient (${response.status})`
        throw new Error(message)
      }
      handleConfigSuccess(payload, 'Ingredient mapping removed.')
    } catch (err) {
      handleConfigFailure(err)
    } finally {
      setConfigLoading(false)
    }
  }, [handleConfigFailure, handleConfigSuccess])

  const handleStapleCreate = useCallback(async () => {
    if (!newStapleName.trim()) {
      setConfigStatus('Staple name is required.')
      return
    }
    const amount = Number.parseFloat(newStapleAmount.replace(',', '.'))
    if (Number.isNaN(amount) || amount <= 0) {
      setConfigStatus('Staple amount must be positive.')
      return
    }
    try {
      setConfigLoading(true)
      const response = await fetch(`${API_BASE}/api/staples`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newStapleName.trim(), amount, unit: newStapleUnit.trim() }),
      })
      const payload = await ensureJson<{ categories?: any; items?: any; staples?: any; staple_label?: string; staple_label_options?: string[]; error?: string }>(response)
      if (!response.ok) {
        const message = payload.error ?? `Failed to add staple (${response.status})`
        throw new Error(message)
      }
      handleConfigSuccess(payload, 'Staple added.')
      setNewStapleName('')
      setNewStapleAmount('1')
      setNewStapleUnit('stk')
    } catch (err) {
      handleConfigFailure(err)
    } finally {
      setConfigLoading(false)
    }
  }, [handleConfigFailure, handleConfigSuccess, newStapleAmount, newStapleName, newStapleUnit])

  const handleStapleSave = useCallback(async (stapleId: number) => {
    const staple = configStaples.find((entry) => entry.id === stapleId)
    if (!staple) {
      return
    }
    if (!staple.name.trim()) {
      setConfigStatus('Staple name cannot be empty.')
      return
    }
    const amount = Number.isFinite(staple.amount) ? staple.amount : 1
    try {
      setConfigLoading(true)
      const response = await fetch(`${API_BASE}/api/staples/${stapleId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: staple.name.trim(), amount, unit: staple.unit.trim() }),
      })
      const payload = await ensureJson<{ categories?: any; items?: any; staples?: any; staple_label?: string; staple_label_options?: string[]; error?: string }>(response)
      if (!response.ok) {
        const message = payload.error ?? `Failed to update staple (${response.status})`
        throw new Error(message)
      }
      handleConfigSuccess(payload, 'Staple updated.')
    } catch (err) {
      handleConfigFailure(err)
    } finally {
      setConfigLoading(false)
    }
  }, [configStaples, handleConfigFailure, handleConfigSuccess])

  const handleStapleDelete = useCallback(async (stapleId: number) => {
    try {
      setConfigLoading(true)
      const response = await fetch(`${API_BASE}/api/staples/${stapleId}`, { method: 'DELETE' })
      const payload = await ensureJson<{ categories?: any; items?: any; staples?: any; staple_label?: string; staple_label_options?: string[]; error?: string }>(response)
      if (!response.ok) {
        const message = payload.error ?? `Failed to delete staple (${response.status})`
        throw new Error(message)
      }
      handleConfigSuccess(payload, 'Staple removed.')
    } catch (err) {
      handleConfigFailure(err)
    } finally {
      setConfigLoading(false)
    }
  }, [handleConfigFailure, handleConfigSuccess])

  const handleStapleLabelSave = useCallback(async () => {
    const label = customStapleLabel.trim() || configStapleLabel.trim()
    if (!label) {
      setConfigStatus('Enter a label before saving.')
      return
    }
    try {
      setConfigLoading(true)
      const response = await fetch(`${API_BASE}/api/staples/label`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label, use_custom: Boolean(customStapleLabel.trim()), custom_label: customStapleLabel.trim() }),
      })
      const payload = await ensureJson<{ categories?: any; items?: any; staples?: any; staple_label?: string; staple_label_options?: string[]; error?: string }>(response)
      if (!response.ok) {
        const message = payload.error ?? `Failed to update label (${response.status})`
        throw new Error(message)
      }
      handleConfigSuccess(payload, 'Staple label saved.')
      setCustomStapleLabel('')
    } catch (err) {
      handleConfigFailure(err)
    } finally {
      setConfigLoading(false)
    }
  }, [configStapleLabel, customStapleLabel, handleConfigFailure, handleConfigSuccess])

  useEffect(() => {
    if (view === 'config' && !configLoaded) {
      fetchConfigData()
    }
  }, [configLoaded, fetchConfigData, view])

  const startCamera = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      pushToast('error', 'Camera access is not supported in this browser.')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', advanced: [{ focusMode: 'continuous' }] as any },
        audio: false,
      })
      mediaStreamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
      }
      setCameraActive(true)
      // Best-effort autofocus: try to enable continuous focus if supported
      try {
        const [track] = stream.getVideoTracks()
        videoTrackRef.current = track || null
        if (track && typeof (track as any).getCapabilities === 'function') {
          const caps = (track as any).getCapabilities?.() || {}
          const canContinuous = Array.isArray(caps.focusMode) && caps.focusMode.includes('continuous')
          if (canContinuous && typeof (track as any).applyConstraints === 'function') {
            await (track as any).applyConstraints({ advanced: [{ focusMode: 'continuous' }] })
          }
          if (caps.focusDistance && typeof caps.focusDistance.min === 'number' && typeof (track as any).applyConstraints === 'function') {
            const min = caps.focusDistance.min
            const max = caps.focusDistance.max
            const mid = (min + max) / 2
            setFocusSupported(true)
            setFocusMin(min)
            setFocusMax(max)
            setFocusValue(mid)
            await (track as any).applyConstraints({ advanced: [{ focusMode: 'manual', focusDistance: mid }] })
          } else {
            setFocusSupported(false)
            setFocusMin(null)
            setFocusMax(null)
            setFocusValue(null)
          }
        }
      } catch {
        // ignore focus attempts
      }
      pushToast('info', 'Camera ready. Capture when the recipe is in frame.')
    } catch (err) {
      pushToast('error', `Unable to access camera: ${(err as Error).message}`)
    }
  }, [pushToast])

  const setManualFocus = useCallback(async (value: number) => {
    setFocusValue(value)
    const track = videoTrackRef.current as any
    if (!track || typeof track.applyConstraints !== 'function') return
    try {
      await track.applyConstraints({ advanced: [{ focusMode: 'manual', focusDistance: value }] })
    } catch {
      /* ignore */
    }
  }, [])

  const capturePhoto = useCallback(() => {
    if (!videoRef.current) {
      pushToast('error', 'Camera is not active.')
      return
    }
    const video = videoRef.current
    const canvas = canvasRef.current
    if (!canvas) {
      pushToast('error', 'Capture canvas not ready.')
      return
    }
    const { videoWidth, videoHeight } = video
    if (!videoWidth || !videoHeight) {
      pushToast('error', 'Camera is still initialising. Try again in a moment.')
      return
    }
    canvas.width = videoWidth
    canvas.height = videoHeight
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      pushToast('error', 'Unable to capture photo.')
      return
    }
    ctx.drawImage(video, 0, 0, videoWidth, videoHeight)
    canvas.toBlob(async (blob) => {
      if (!blob) {
        pushToast('error', 'Failed to capture photo.')
        return
      }
      const file = new File([blob], `capture-${Date.now()}.jpg`, { type: blob.type || 'image/jpeg' })
      if (imagePreviewUrl) {
        URL.revokeObjectURL(imagePreviewUrl)
      }
      const url = URL.createObjectURL(blob)
      setImagePreviewUrl(url)
      setImageFilename(file.name)
      await processImage(file)
    }, 'image/jpeg', 0.92)
  }, [imagePreviewUrl, processImage, pushToast])

  const gatherIngredientPayload = useCallback((rows: IngredientFormRow[], { requireAmount }: { requireAmount: boolean }) => {
    return rows
      .map((row) => ({
        navn: row.navn.trim(),
        amount: parseAmountInput(row.amount),
        unit: row.unit.trim(),
      }))
      .filter(({ navn, amount }) => navn && (!requireAmount || Number.isFinite(amount)))
      .map(({ navn, amount, unit }) => ({ navn, amount: Number.isFinite(amount) ? amount : 1, unit }))
  }, [])

  const buildRecipePayload = useCallback((name: string, placement: string, servings: number, ingredientRows: IngredientFormRow[], extraRows: IngredientFormRow[]) => {
    const trimmedName = name.trim()
    if (!trimmedName) {
      throw new Error('Please provide a recipe name.')
    }
    if (!Number.isFinite(servings) || servings < 0) {
      throw new Error('Servings must be a non-negative number.')
    }
    const ingredients = gatherIngredientPayload(ingredientRows, { requireAmount: true })
    if (!ingredients.length) {
      throw new Error('Add at least one ingredient with an amount.')
    }
    const extras = gatherIngredientPayload(extraRows, { requireAmount: false })
    const payload: any = {
      navn: trimmedName,
      placering: placement.trim(),
      antal: servings,
      ingredienser: ingredients,
    }
    if (extras.length) {
      payload.extras = extras
    }
    return payload
  }, [gatherIngredientPayload])

  const gatherFormPayload = useCallback(() => buildRecipePayload(formName, formPlacement, formServings, ingredientRows, extraRows), [buildRecipePayload, formName, formPlacement, formServings, ingredientRows, extraRows])

  const handleRecipeSubmit = useCallback(async () => {
    try {
      const payload = gatherFormPayload()
      const response = await fetch(`${API_BASE}/api/recipes`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      })
      const result = await ensureJson<{ recipe?: Recipe; error?: string }>(response)
      if (!response.ok) {
        const message = result.error ?? `Failed to save recipe (${response.status})`
        throw new Error(message)
      }
      pushToast('success', `${result.recipe?.navn ?? payload.navn} saved.`)
      await loadRecipes()
      resetForm()
    } catch (err) {
      pushToast('error', (err as Error).message)
    }
  }, [gatherFormPayload, loadRecipes, pushToast, resetForm])

  const buildEditPayload = useCallback(() => {
    if (!editSlug) {
      throw new Error('Select a recipe to edit.')
    }
    const base = buildRecipePayload(editName, editPlacement, editServings, editIngredients, editExtras)
    return {
      ...base,
      slug: editSlugInput.trim(),
      is_blacklisted: editIsBlacklisted,
      is_whitelisted: editIsWhitelisted,
    }
  }, [buildRecipePayload, editExtras, editIngredients, editIsBlacklisted, editIsWhitelisted, editName, editPlacement, editServings, editSlug, editSlugInput])

  const handleEditSubmit = useCallback(async () => {
    if (!editSlug) {
      pushToast('info', 'Select a recipe to edit.')
      return
    }
    try {
      const payload = buildEditPayload()
      const response = await fetch(`${API_BASE}/api/recipes/${encodeURIComponent(editSlug)}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      })
      const result = await ensureJson<{ recipe?: Recipe; error?: string }>(response)
      if (!response.ok) {
        const message = result.error ?? `Failed to update recipe (${response.status})`
        throw new Error(message)
      }
      const updated = result.recipe
      if (updated) {
        setRecipes((prev) => prev.map((recipe) => (recipe.slug === editSlug ? updated : recipe)))
        handleEditSelect(updated.slug)
      } else {
        await loadRecipes()
        handleEditSelect(editSlugInput.trim() || editSlug)
      }
      setEditStatus('Changes saved.')
      pushToast('success', 'Recipe updated.')
    } catch (err) {
      const message = (err as Error).message
      setEditStatus(message)
      pushToast('error', message)
    }
  }, [buildEditPayload, editSlug, editSlugInput, handleEditSelect, loadRecipes, pushToast, setRecipes])

  const addToSelection = useCallback((recipe: Recipe, initialServings?: number) => {
    setSelection((prev) => {
      const existing = prev[recipe.slug]
      const nextServings = initialServings ?? (existing ? existing.servings + 1 : Math.max(1, recipe.antal))
      return {
        ...prev,
        [recipe.slug]: {
          recipe,
          servings: nextServings,
        },
      }
    })
  }, [])

  const removeFromSelection = useCallback((slug: string) => {
    setSelection((prev) => {
      const { [slug]: _removed, ...rest } = prev
      return rest
    })
  }, [])

  const adjustServings = useCallback((slug: string, delta: number) => {
    setSelection((prev) => {
      const current = prev[slug]
      if (!current) return prev
      const nextServings = Math.max(1, current.servings + delta)
      return {
        ...prev,
        [slug]: {
          recipe: current.recipe,
          servings: nextServings,
        },
      }
    })
  }, [])

  const setFreezerServings = useCallback((slug: string) => {
    setSelection((prev) => {
      const current = prev[slug]
      if (!current) return prev
      return {
        ...prev,
        [slug]: {
          recipe: current.recipe,
          servings: 0,
        },
      }
    })
  }, [])

  const clearSelection = useCallback(() => setSelection({}), [])

  const eligibleRecipes = useMemo(() => recipes.filter((recipe) => !recipe.is_blacklisted || recipe.is_whitelisted), [recipes])

  const spinMenu = useCallback(() => {
    if (!eligibleRecipes.length) {
      setSpinnerResults([])
      return
    }
    const pool = [...eligibleRecipes]
    const picks: Recipe[] = []
    const count = Math.min(6, pool.length)
    for (let index = 0; index < count; index += 1) {
      const choiceIndex = Math.floor(Math.random() * pool.length)
      const [choice] = pool.splice(choiceIndex, 1)
      picks.push(choice)
    }
    setSpinnerResults(picks)
  }, [eligibleRecipes])

  useEffect(() => {
    if (!loading && !error && eligibleRecipes.length && spinnerResults.length === 0) {
      spinMenu()
    }
  }, [eligibleRecipes, error, loading, spinnerResults.length, spinMenu])

  const searchTerm = search.trim().toLowerCase()
  const hasSearch = searchTerm.length > 0

  const filteredRecipes = useMemo(() => {
    if (!hasSearch) {
      return eligibleRecipes
    }
    return eligibleRecipes.filter((recipe) => {
      const nameMatch = recipe.navn.toLowerCase().includes(searchTerm)
      const ingredientMatch = Object.keys(recipe.ingredienser || {}).some((key) => key.toLowerCase().includes(searchTerm))
      const extrasMatch = Object.keys(recipe.extras || {}).some((key) => key.toLowerCase().includes(searchTerm))
      return nameMatch || ingredientMatch || extrasMatch
    })
  }, [eligibleRecipes, hasSearch, searchTerm])

  const filteredEditRecipes = useMemo(() => {
    const term = editSearch.trim().toLowerCase()
    if (!term) {
      return recipes
    }
    return recipes.filter((recipe) => {
      const nameMatch = recipe.navn.toLowerCase().includes(term)
      const slugMatch = (recipe.slug || '').toLowerCase().includes(term)
      const ingredientMatch = Object.keys(recipe.ingredienser || {}).some((key) => key.toLowerCase().includes(term))
      const extrasMatch = Object.keys(recipe.extras || {}).some((key) => key.toLowerCase().includes(term))
      return nameMatch || slugMatch || ingredientMatch || extrasMatch
    })
  }, [recipes, editSearch])

  const selectionEntries = Object.values(selection)
  const hasSelection = selectionEntries.length > 0

  const displayedRecipes = hasSearch ? filteredRecipes.slice(0, 24) : spinnerResults

  useEffect(() => {
    if (view !== 'edit') {
      return
    }
    if (!recipes.length) {
      populateEditForm(null)
      return
    }
    const list = filteredEditRecipes
    if (!list.length) {
      setEditSlug(null)
      setEditStatus(editSearch ? 'No recipes match that search.' : 'No recipes available yet.')
      return
    }
    const nextSlug = editSlug && list.some((recipe) => recipe.slug === editSlug) ? editSlug : list[0].slug
    if (!nextSlug) {
      populateEditForm(null)
      return
    }
    if (nextSlug !== editSlug) {
      handleEditSelect(nextSlug)
    }
  }, [editSearch, editSlug, filteredEditRecipes, handleEditSelect, populateEditForm, recipes, view])

  // Track the signature of the selection that was last successfully rendered,
  // so we can detect when the user changed picks and need to re-generate.
  const [lastRenderedSig, setLastRenderedSig] = useState<string>('')
  const selectionSignature = useMemo(() => (
    Object.values(selection)
      .map((entry) => `${entry.recipe.slug}:${entry.servings}`)
      .sort()
      .join('|')
  ), [selection])

  const runGenerateMenu = useCallback(async ({ silent }: { silent: boolean }) => {
    if (!hasSelection) return
    setExporting(true)
    if (!silent) {
      setMenuMarkdown('')
      setMenuPreview(null)
    }
    try {
      const menuData = Object.values(selection).reduce<Record<string, number>>((acc, entry) => {
        acc[entry.recipe.navn] = entry.servings
        return acc
      }, {})

      const response = await fetch(`${API_BASE}/api/menu/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ menu_data: menuData }),
      })
      const payload = await ensureJson<{ markdown?: string; error?: string }>(response)
      if (!response.ok) {
        const message = payload.error ?? `Failed with status ${response.status}`
        throw new Error(message)
      }
      const markdown = payload.markdown ?? ''
      setMenuMarkdown(markdown)

      const parts = markdown.split(/^#\s+Shopping/m)
      const menuPart = parts[0] ?? ''
      const shoppingPart = parts[1] ? `## Shopping${parts[1]}` : ''
      const menuHtml = (await marked.parse(menuPart, { breaks: true })) as string
      const shoppingHtml = shoppingPart ? ((await marked.parse(shoppingPart, { breaks: true })) as string) : ''
      setMenuPreview({ menuHtml, shoppingHtml })
      setLastRenderedSig(selectionSignature)
      if (!silent) pushToast('success', 'Menu ready to print.')
    } catch (err) {
      pushToast('error', (err as Error).message)
    } finally {
      setExporting(false)
    }
  }, [selection, hasSelection, pushToast, selectionSignature])

  // Auto-generate when entering shopping view (or when selection changed since last render)
  useEffect(() => {
    if (view !== 'shopping') return
    if (!hasSelection) return
    if (exporting) return
    if (lastRenderedSig === selectionSignature && menuPreview) return
    void runGenerateMenu({ silent: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, hasSelection, selectionSignature])

  const handleDownloadMarkdown = useCallback(() => {
    if (!menuMarkdown) return
    const blob = new Blob([menuMarkdown], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    const date = new Date()
    const stamp = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
    link.href = url
    link.download = `menu-${stamp}.md`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    pushToast('info', 'Markdown downloaded.')
  }, [menuMarkdown, pushToast])

  const handleCopyMarkdown = useCallback(async () => {
    if (!menuMarkdown) return
    try {
      await navigator.clipboard.writeText(menuMarkdown)
      pushToast('success', 'Copied markdown to clipboard.')
    } catch (err) {
      pushToast('error', `Clipboard error: ${(err as Error).message}`)
    }
  }, [menuMarkdown, pushToast])

  const handleDownloadPdf = useCallback(async () => {
    if (!menuPreview || !pdfPreviewRef.current) {
      pushToast('info', 'Generate the shopping list first.')
      return
    }
    try {
      await (html2pdf as any)()
        .set({
          margin: 12,
          filename: 'shopping.pdf',
          html2canvas: { scale: 2, useCORS: true },
          pagebreak: { mode: ['css', 'legacy'] },
          jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
        })
        .from(pdfPreviewRef.current)
        .save()
      pushToast('success', 'PDF downloaded.')
    } catch (err) {
      pushToast('error', `PDF generation failed: ${(err as Error).message}`)
    }
  }, [menuPreview, pushToast])

  const handleRenameSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      if (!renameFrom.trim() || !renameTo.trim()) {
        pushToast('info', 'Provide both source and target names.')
        return
      }
      setRenameSubmitting(true)
      setRenameResult(null)
      setRenameConflicts(null)
      try {
        const response = await fetch(`${API_BASE}/api/ingredients/rename`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            from: renameFrom,
            to: renameTo,
            include_extras: renameIncludeExtras,
            case_insensitive: renameCaseInsensitive,
            force: renameForce,
          }),
        })
        const payload = await response.json()
        if (!response.ok) {
          const message = payload.error ?? `Rename failed with status ${response.status}`
          throw new Error(message)
        }
        const updated = payload.updated_count ?? 0
        const conflicts = payload.conflicts ?? []
        setRenameResult(`${updated} recipe${updated === 1 ? '' : 's'} updated.`)
        if (conflicts.length) {
          const conflictSummary = conflicts
            .map((conflict: { name: string; field: string; reason: string }) => `${conflict.name} (${conflict.field}): ${conflict.reason}`)
            .join('\n')
          setRenameConflicts(conflictSummary)
        }
        pushToast('success', `Renamed ingredients in ${updated} recipe${updated === 1 ? '' : 's'}.`)
        await loadRecipes()
      } catch (err) {
        const message = (err as Error).message
        setRenameResult(null)
        setRenameConflicts(null)
        pushToast('error', message)
      } finally {
        setRenameSubmitting(false)
      }
    },
    [renameFrom, renameTo, renameIncludeExtras, renameCaseInsensitive, renameForce, pushToast, loadRecipes],
  )

  // Primary destinations (3 only) + secondary sub-tabs under each.
  const planActive = view === 'planner' || view === 'shopping'
  const recipesActive = view === 'add' || view === 'edit' || view === 'tools'
  const settingsActive = view === 'config'

  return (
    <div className="app-shell min-h-screen px-4 py-6 pb-24 text-muted sm:px-6 sm:py-8 lg:px-10 lg:pb-10">
      <div className="toast-stack no-print">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`rounded-full px-4 py-2 text-sm shadow-lg backdrop-blur transition ${
              toast.kind === 'success'
                ? 'bg-emerald-500/95 text-white'
                : toast.kind === 'error'
                  ? 'bg-danger/95 text-white'
                  : 'bg-brand-surface/95 text-white'
            }`}
          >
            {toast.message}
          </div>
        ))}
      </div>

      <div className="mx-auto flex max-w-6xl flex-col gap-6 pb-24 lg:gap-8 lg:pb-0">
        {/* Slim header: title + top nav (desktop) / title only (mobile, nav lives at bottom) */}
        <header className="no-print rounded-panel bg-brand-surface/90 px-5 py-4 shadow-panel backdrop-blur lg:px-6 lg:py-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <button
                type="button"
                className="font-display text-2xl font-semibold tracking-tight text-white transition hover:text-brand-accent lg:text-3xl"
                onClick={() => goToView('planner')}
                aria-label="Menu Spinner home"
              >
                Menu Spinner
              </button>
              <span className="hidden text-xs uppercase tracking-[0.25em] text-white/40 sm:inline">
                {loading ? 'Syncing…' : `${eligibleRecipes.length} recipes`}
              </span>
            </div>
            <nav className="hidden items-center gap-2 lg:flex" aria-label="Primary">
              {([
                { key: 'planner' as View, label: 'Plan', active: planActive },
                { key: 'edit' as View, label: 'Recipes', active: recipesActive },
                { key: 'config' as View, label: 'Settings', active: settingsActive },
              ]).map(({ key, label, active }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => goToView(key)}
                  className={`rounded-full border px-5 py-2 text-sm font-medium transition ${
                    active
                      ? 'border-brand-accent bg-brand-accent text-brand-dark shadow-lg'
                      : 'border-white/15 bg-brand-dark/40 text-white/70 hover:text-white'
                  }`}
                  aria-current={active ? 'page' : undefined}
                >
                  {label}
                </button>
              ))}
            </nav>
          </div>
        </header>

        {/* Secondary sub-tabs under the active primary destination (desktop & mobile) */}
        {(recipesActive || planActive) && (
          <div className="no-print -mt-2 flex flex-wrap items-center gap-2 px-1 text-xs sm:text-sm">
            {planActive && (
              <>
                <SubTab label="Pick recipes" active={view === 'planner'} onClick={() => goToView('planner')} />
                <SubTab label={hasSelection ? `Print menu (${Object.keys(selection).length})` : 'Print menu'} active={view === 'shopping'} onClick={() => hasSelection && goToView('shopping')} disabled={!hasSelection} />
              </>
            )}
            {recipesActive && (
              <>
                <SubTab label="All recipes" active={view === 'edit'} onClick={() => goToView('edit')} />
                <SubTab label="Add new" active={view === 'add'} onClick={() => goToView('add')} />
                <SubTab label="Bulk rename" active={view === 'tools'} onClick={() => goToView('tools')} />
              </>
            )}
          </div>
        )}

        {view === 'planner' && (
          <>
            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
              <section className="rounded-panel bg-brand-surface/80 p-5 shadow-panel backdrop-blur lg:p-6">
                {/* Command row: search + suggest */}
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                  <label className="flex flex-1 items-center gap-3 rounded-full border border-white/10 bg-brand-dark/50 px-4 py-2.5 text-sm text-white/80 focus-within:border-brand-accent">
                    <span aria-hidden="true" className="text-white/40">🔍</span>
                    <input
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                      placeholder="Search recipes or ingredients…"
                      className="flex-1 border-none bg-transparent text-white outline-none placeholder:text-white/40"
                      aria-label="Search recipes"
                    />
                    {search && (
                      <button type="button" className="text-white/60 hover:text-white" onClick={() => setSearch('')} aria-label="Clear search">
                        ✕
                      </button>
                    )}
                  </label>
                  <button
                    type="button"
                    className="inline-flex items-center justify-center gap-2 rounded-full border border-white/15 bg-brand-dark/40 px-4 py-2.5 text-sm font-medium text-white transition hover:border-brand-accent/60 hover:text-brand-accent disabled:opacity-50"
                    onClick={spinMenu}
                    disabled={loading || !eligibleRecipes.length}
                    title="Show 6 random recipe suggestions"
                  >
                    <span aria-hidden="true">🎲</span>
                    Suggest 6
                  </button>
                </div>

                {/* Inline status row */}
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-white/50">
                  <span>
                    {hasSearch
                      ? `${filteredRecipes.length} matching`
                      : spinnerResults.length
                        ? 'Random suggestions — tap a card to add'
                        : 'Tap a card to add it to the menu'}
                  </span>
                  {!hasSearch && eligibleRecipes.length > 0 && (
                    <button
                      type="button"
                      className="rounded-full px-2 py-0.5 text-white/60 transition hover:text-white"
                      onClick={() => { setSearch(''); spinMenu() }}
                    >
                      Reshuffle
                    </button>
                  )}
                </div>

                <div className="mt-5 space-y-5">
                  {loading && <p className="text-sm text-white/70">Loading recipes…</p>}

                  {error && (
                    <p className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
                      {error}
                    </p>
                  )}

                  {!loading && !error && !eligibleRecipes.length && (
                    <div className="rounded-2xl border border-dashed border-white/15 bg-black/20 px-5 py-8 text-center text-sm text-white/70">
                      <p className="font-medium text-white">No recipes yet</p>
                      <p className="mt-1">Add your first recipe — it only takes a photo.</p>
                      <button
                        type="button"
                        className="mt-4 inline-flex items-center gap-2 rounded-full bg-brand-accent px-4 py-2 text-sm font-medium text-brand-dark"
                        onClick={() => goToView('add')}
                      >
                        + Add recipe
                      </button>
                    </div>
                  )}

                  {!loading && !error && hasSearch && !filteredRecipes.length && (
                    <p className="text-sm text-white/70">No recipes match that search.</p>
                  )}

                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {displayedRecipes.map((recipe) => {
                      const selected = Boolean(selection[recipe.slug])
                      const servings = selection[recipe.slug]?.servings ?? 0
                      return (
                        <div
                          key={recipe.slug}
                          className={`relative flex flex-col gap-1 rounded-2xl border bg-white/5 px-4 py-3 text-left text-sm text-white transition ${
                            selected ? 'recipe-card-chosen' : 'border-white/10 hover:border-brand-accent/40 hover:bg-brand-dark/40'
                          }`}
                        >
                          <button
                            type="button"
                            className="absolute right-2 top-2 inline-flex h-8 w-8 items-center justify-center rounded-full border border-white/15 bg-brand-dark/70 text-base font-medium text-white transition hover:border-brand-accent hover:text-brand-accent"
                            onClick={() => addToSelection(recipe)}
                            aria-label={selected ? `Add another plate of ${recipe.navn}` : `Add ${recipe.navn} to menu`}
                            title={selected ? 'Add another plate' : 'Add to menu'}
                          >
                            {selected ? '✓' : '+'}
                          </button>
                          <button
                            type="button"
                            className="text-left"
                            onClick={() => addToSelection(recipe)}
                          >
                            <p className="pr-10 font-medium">{recipe.navn}</p>
                            <p className="mt-0.5 text-xs text-white/50">
                              {recipe.antal} plates · {Object.keys(recipe.ingredienser).length} ingredients
                              {recipe.placering ? ` · ${recipe.placering}` : ''}
                            </p>
                          </button>
                          {selected && (
                            <p className="mt-1 text-xs text-brand-accent">
                              On menu · {servings === 0 ? 'from freezer' : `${servings} plate${servings === 1 ? '' : 's'}`}
                            </p>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              </section>

              {/* Right sidebar (desktop) / sticky bottom (mobile) */}
              <aside className="rounded-panel bg-brand-dark/80 p-5 shadow-panel backdrop-blur lg:p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="font-display text-xl text-white lg:text-2xl">This week</h2>
                    <p className="text-xs text-white/50">{selectionEntries.length} recipe{selectionEntries.length === 1 ? '' : 's'} chosen</p>
                  </div>
                  <button
                    type="button"
                    className="text-xs uppercase tracking-[0.2em] text-white/60 transition hover:text-white disabled:opacity-30"
                    onClick={clearSelection}
                    disabled={!hasSelection}
                  >
                    Clear
                  </button>
                </div>

                <div className="mt-5 space-y-2">
                  {!hasSelection && (
                    <p className="rounded-xl border border-dashed border-white/10 px-4 py-6 text-center text-sm text-white/50">
                      Tap a recipe card to add it.
                    </p>
                  )}

                  {selectionEntries.map(({ recipe, servings }) => {
                    const fromFreezer = servings === 0
                    return (
                      <div key={recipe.slug} className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white">
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-medium">{recipe.navn}</p>
                          {recipe.placering && <p className="truncate text-[11px] text-white/40">{recipe.placering}</p>}
                        </div>
                        <button
                          type="button"
                          className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-xs transition ${
                            fromFreezer
                              ? 'border-brand-accent/60 bg-brand-accent/10 text-brand-accent'
                              : 'border-white/10 text-white/70 hover:border-brand-accent/40 hover:text-white'
                          }`}
                          onClick={() => fromFreezer ? adjustServings(recipe.slug, 1) : setFreezerServings(recipe.slug)}
                          aria-label={fromFreezer ? `${recipe.navn} from freezer — switch to plates` : `Mark ${recipe.navn} as from freezer`}
                          title={fromFreezer ? 'From freezer (click to switch to plates)' : 'Mark as from freezer'}
                        >
                          {fromFreezer ? '❄ Freezer' : (
                            <>
                              <span aria-hidden="true">🍽</span>
                              <span className="tabular-nums">{servings}</span>
                            </>
                          )}
                        </button>
                        {!fromFreezer && (
                          <div className="flex items-center gap-1">
                            <button
                              type="button"
                              className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-white/10 text-white/70 transition hover:border-brand-accent hover:text-white"
                              onClick={() => adjustServings(recipe.slug, -1)}
                              aria-label={`Decrease plates for ${recipe.navn}`}
                            >
                              −
                            </button>
                            <button
                              type="button"
                              className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-white/10 text-white/70 transition hover:border-brand-accent hover:text-white"
                              onClick={() => adjustServings(recipe.slug, 1)}
                              aria-label={`Increase plates for ${recipe.navn}`}
                            >
                              +
                            </button>
                          </div>
                        )}
                        <button
                          type="button"
                          className="inline-flex h-7 w-7 items-center justify-center rounded-full text-white/40 transition hover:text-danger"
                          onClick={() => removeFromSelection(recipe.slug)}
                          aria-label={`Remove ${recipe.navn} from menu`}
                          title="Remove"
                        >
                          ✕
                        </button>
                      </div>
                    )
                  })}
                </div>

                <button
                  type="button"
                  className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-full bg-brand-accent px-5 py-3 text-sm font-semibold text-brand-dark transition hover:translate-y-[1px] disabled:cursor-not-allowed disabled:opacity-40"
                  onClick={() => goToView('shopping')}
                  disabled={!hasSelection}
                >
                  Print menu →
                </button>
              </aside>
            </div>

            {/* Floating mobile CTA — visible only when something is chosen, sits above the bottom tab bar */}
            {hasSelection && (
              <div className="no-print pointer-events-none fixed inset-x-0 z-30 flex justify-center px-4 lg:hidden" style={{ bottom: 'calc(env(safe-area-inset-bottom, 0) + 4.25rem)' }}>
                <button
                  type="button"
                  className="pointer-events-auto inline-flex items-center gap-2 rounded-full bg-brand-accent px-6 py-3 text-sm font-semibold text-brand-dark shadow-2xl shadow-brand-accent/40"
                  onClick={() => goToView('shopping')}
                >
                  {selectionEntries.length} recipe{selectionEntries.length === 1 ? '' : 's'} · Print menu →
                </button>
              </div>
            )}
          </>
        )}

        {view === 'add' && (
          <div className="mx-auto w-full max-w-3xl">
            {cameraActive && (
              <div
                data-testid="camera-modal"
                className="fixed inset-0 z-50 flex flex-col bg-black/90 p-4"
                role="dialog"
                aria-label="Camera preview"
              >
                <div className="relative flex-1 overflow-hidden rounded-2xl border border-white/10 bg-black/40">
                  <video
                    ref={videoRef}
                    className="h-full w-full object-contain"
                    playsInline
                    muted
                  />
                  {imageProcessing && (
                    <div
                      data-testid="processing-overlay"
                      className="absolute inset-0 flex items-center justify-center bg-black/50"
                    >
                      <div className="h-14 w-14 animate-spin rounded-full border-4 border-white/20 border-t-brand-accent" />
                    </div>
                  )}
                </div>
                <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
                  <button
                    type="button"
                    className="rounded-full bg-brand-accent px-6 py-3 font-semibold text-brand-dark transition hover:translate-y-[1px]"
                    onClick={capturePhoto}
                  >
                    📸 Capture photo
                  </button>
                  {focusSupported && focusMin != null && focusMax != null && focusValue != null && (
                    <label className="flex items-center gap-2 text-xs text-white/80">
                      <span>Focus</span>
                      <input
                        type="range"
                        min={focusMin}
                        max={focusMax}
                        step={((focusMax - focusMin) || 1) / 100}
                        value={focusValue}
                        onChange={(e) => setManualFocus(Number.parseFloat(e.target.value))}
                        aria-label="Focus"
                      />
                    </label>
                  )}
                  {!focusSupported && (
                    <span className="text-xs text-white/50">Manual focus not supported on this camera</span>
                  )}
                  <button
                    type="button"
                    className="rounded-full border border-white/30 px-6 py-3 text-white/90 transition hover:bg-white/10"
                    onClick={stopCamera}
                  >
                    Close
                  </button>
                </div>
              </div>
            )}

            <section className="rounded-panel bg-brand-surface/80 p-5 shadow-panel backdrop-blur lg:p-6">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="font-display text-xl text-white lg:text-2xl">Add a recipe</h2>
                  <p className="text-sm text-white/60">Snap a photo, upload, or type it in.</p>
                </div>
                <button
                  type="button"
                  className="rounded-full border border-white/15 bg-brand-dark/40 px-3 py-1.5 text-xs text-white/70 transition hover:text-white"
                  onClick={() => resetForm()}
                >
                  Reset
                </button>
              </div>

              {/* Mode chips */}
              <div role="tablist" aria-label="Input method" className="mt-5 inline-flex w-full rounded-full border border-white/10 bg-brand-dark/40 p-1 text-xs sm:text-sm">
                {([
                  { key: 'photo' as const, label: 'Upload photo', icon: '🖼️' },
                  { key: 'camera' as const, label: 'Camera', icon: '📷' },
                  { key: 'manual' as const, label: 'Manual', icon: '✏️' },
                ]).map(({ key, label, icon }) => (
                  <button
                    key={key}
                    type="button"
                    role="tab"
                    aria-selected={addInputMode === key}
                    onClick={() => setAddInputMode(key)}
                    className={`flex-1 rounded-full px-3 py-2 font-medium transition ${
                      addInputMode === key
                        ? 'bg-brand-accent text-brand-dark shadow'
                        : 'text-white/70 hover:text-white'
                    }`}
                  >
                    <span className="mr-1.5" aria-hidden="true">{icon}</span>
                    {label}
                  </button>
                ))}
              </div>

              {/* Input area — content varies by mode */}
              <div className="mt-4">
                {addInputMode === 'photo' && (
                  <div
                    className={`rounded-3xl border-2 border-dashed px-6 py-8 text-center text-sm transition ${dropActive ? 'border-brand-accent bg-brand-dark/30' : 'border-white/15 bg-black/20'} ${imageProcessing ? 'opacity-70' : ''}`}
                    onDrop={onDrop}
                    onDragOver={onDragOver}
                    onDragEnter={onDragEnter}
                    onDragLeave={onDragLeave}
                    role="button"
                    tabIndex={0}
                    onClick={() => fileInputRef.current?.click()}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        fileInputRef.current?.click()
                      }
                    }}
                  >
                    <div aria-hidden="true" className="text-3xl">🖼️</div>
                    <p className="mt-2 font-medium text-white">Drop a recipe photo here</p>
                    <p className="mt-1 text-xs text-white/60">…or click to choose a file. JPG / PNG.</p>
                    {imageProcessing && <p className="mt-3 text-xs text-brand-accent">Reading recipe… hold tight.</p>}
                  </div>
                )}

                {addInputMode === 'camera' && (
                  <div className="rounded-2xl border border-white/10 bg-black/30 p-4 text-xs text-white/70">
                    <p className="text-sm text-white">Use your device camera to snap the page.</p>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        className="rounded-full bg-brand-accent px-5 py-2.5 text-sm font-semibold text-brand-dark transition hover:translate-y-[1px]"
                        onClick={startCamera}
                      >
                        📷 Start camera
                      </button>
                      <span className="text-[11px] text-white/40">Live preview opens full-screen.</span>
                    </div>
                  </div>
                )}

                {addInputMode === 'manual' && (
                  <p className="rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-xs text-white/60">
                    Skip the photo and just fill in the form below.
                  </p>
                )}

                <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={onFileInputChange} />

                {imagePreviewUrl && (
                  <div className="mt-3 rounded-2xl border border-white/10 bg-black/30 p-3 text-xs text-white/70">
                    <div className="flex items-start gap-3">
                      <img src={imagePreviewUrl} alt={imageFilename ?? 'Recipe photo'} className="h-20 w-20 flex-shrink-0 rounded-lg object-cover" />
                      <div className="min-w-0">
                        <p className="font-medium text-white">Photo attached</p>
                        {imageFilename && <p className="mt-0.5 truncate text-[11px] text-white/50">{imageFilename}</p>}
                        <p className="mt-1 text-[11px] text-white/40">AI will pre-fill the form below — review before saving.</p>
                      </div>
                    </div>
                  </div>
                )}

                {(addInputMode === 'photo' || addInputMode === 'camera') && (
                  <label className="mt-3 block text-xs text-white/80">
                    <span className="mb-1 block text-[11px] uppercase tracking-[0.2em] text-white/50">Hint for the AI (optional)</span>
                    <textarea
                      value={imagePrompt}
                      onChange={handlePromptChange}
                      rows={2}
                      className="w-full resize-none rounded-xl border border-white/10 bg-brand-dark/50 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                      placeholder='e.g. "metric units" or "ignore watermark"'
                    />
                  </label>
                )}

                {generatedYaml && (
                  <details className="mt-3 text-xs text-white/60">
                    <summary className="cursor-pointer select-none hover:text-white">AI raw output</summary>
                    <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded-lg bg-black/60 p-3 text-[11px]">{generatedYaml}</pre>
                  </details>
                )}
              </div>

              <canvas ref={canvasRef} className="hidden" />
            </section>

            {/* Form */}
            <section className="mt-5 rounded-panel bg-brand-dark/70 p-5 shadow-panel backdrop-blur lg:p-6">
              <h3 className="font-display text-lg text-white">Recipe details</h3>
              <p className="text-xs text-white/50">Edit anything below — these are what gets saved.</p>

              <div className="mt-4 grid gap-4 sm:grid-cols-[minmax(0,1fr)_120px]">
                <label className="flex flex-col text-xs text-white/70">
                  <span className="mb-1 text-white/50">Recipe name</span>
                  <input
                    value={formName}
                    onChange={(event) => setFormName(event.target.value)}
                    className="rounded-xl border border-white/10 bg-brand-surface/60 px-3 py-2.5 text-sm text-white outline-none focus:border-brand-accent"
                    placeholder="Recipe title"
                  />
                </label>
                <label className="flex flex-col text-xs text-white/70">
                  <span className="mb-1 text-white/50">Plates</span>
                  <input
                    type="number"
                    min={0}
                    value={formServings}
                    onChange={(event) => setFormServings(Math.max(0, Number.parseInt(event.target.value, 10) || 0))}
                    className="rounded-xl border border-white/10 bg-brand-surface/60 px-3 py-2.5 text-sm text-white outline-none focus:border-brand-accent"
                  />
                </label>
                <label className="flex flex-col text-xs text-white/70 sm:col-span-2">
                  <span className="mb-1 text-white/50">Placement (where to find it)</span>
                  <input
                    value={formPlacement}
                    onChange={(event) => setFormPlacement(event.target.value)}
                    className="rounded-xl border border-white/10 bg-brand-surface/60 px-3 py-2.5 text-sm text-white outline-none focus:border-brand-accent"
                    placeholder="Cookbook, page, or source"
                  />
                </label>
              </div>

              <div className="mt-6">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-semibold uppercase tracking-[0.15em] text-white/60">Ingredients</h4>
                  <button type="button" className="rounded-full border border-white/15 px-3 py-1 text-xs text-white/80 transition hover:text-white" onClick={addIngredientRow}>+ Add row</button>
                </div>
                <div className="mt-3 space-y-2">
                  {ingredientRows.map((row) => (
                    <div key={row.id} className="grid gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-white/80 sm:grid-cols-[minmax(0,1fr)_90px_70px_auto] sm:items-center">
                      <input
                        value={row.navn}
                        onChange={(event) => updateIngredientRow(row.id, { navn: event.target.value })}
                        placeholder="Ingredient"
                        className="rounded-lg border border-white/10 bg-brand-surface/50 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                      />
                      <input
                        value={row.amount}
                        onChange={(event) => updateIngredientRow(row.id, { amount: event.target.value })}
                        placeholder="Amount"
                        className="rounded-lg border border-white/10 bg-brand-surface/50 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                      />
                      <input
                        value={row.unit}
                        onChange={(event) => updateIngredientRow(row.id, { unit: event.target.value })}
                        placeholder="Unit"
                        className="rounded-lg border border-white/10 bg-brand-surface/50 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                      />
                      <button
                        type="button"
                        className="inline-flex h-9 w-9 items-center justify-center justify-self-end rounded-full text-white/40 transition hover:text-danger"
                        onClick={() => removeIngredientRow(row.id)}
                        aria-label="Remove ingredient row"
                        title="Remove"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-6">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-semibold uppercase tracking-[0.15em] text-white/60">Extras</h4>
                  <button type="button" className="rounded-full border border-white/15 px-3 py-1 text-xs text-white/80 transition hover:text-white" onClick={addExtraRow}>+ Add extra</button>
                </div>
                {extraRows.length === 0 && <p className="mt-2 text-xs text-white/50">Sides to also buy (salad, pita, toppings).</p>}
                <div className="mt-3 space-y-2">
                  {extraRows.map((row) => (
                    <div key={row.id} className="grid gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-white/80 sm:grid-cols-[minmax(0,1fr)_90px_70px_auto] sm:items-center">
                      <input
                        value={row.navn}
                        onChange={(event) => updateExtraRow(row.id, { navn: event.target.value })}
                        placeholder="Extra item"
                        className="rounded-lg border border-white/10 bg-brand-surface/50 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                      />
                      <input
                        value={row.amount}
                        onChange={(event) => updateExtraRow(row.id, { amount: event.target.value })}
                        placeholder="Amount"
                        className="rounded-lg border border-white/10 bg-brand-surface/50 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                      />
                      <input
                        value={row.unit}
                        onChange={(event) => updateExtraRow(row.id, { unit: event.target.value })}
                        placeholder="Unit"
                        className="rounded-lg border border-white/10 bg-brand-surface/50 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                      />
                      <button
                        type="button"
                        className="inline-flex h-9 w-9 items-center justify-center justify-self-end rounded-full text-white/40 transition hover:text-danger"
                        onClick={() => removeExtraRow(row.id)}
                        aria-label="Remove extra row"
                        title="Remove"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
                <button
                  type="button"
                  className="rounded-full border border-white/15 bg-brand-dark/40 px-4 py-2.5 text-sm text-white/80 transition hover:text-white"
                  onClick={() => goToView('edit')}
                >
                  ← All recipes
                </button>
                <button
                  type="button"
                  className="inline-flex items-center justify-center gap-2 rounded-full bg-brand-accent px-6 py-3 text-sm font-semibold text-brand-dark transition hover:translate-y-[1px]"
                  onClick={handleRecipeSubmit}
                >
                  💾 Save recipe
                </button>
              </div>
            </section>
          </div>
        )}

        {view === 'edit' && (
          <div className="grid gap-6 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
            <section className="rounded-panel bg-brand-surface/80 p-5 shadow-panel backdrop-blur lg:p-6">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="font-display text-xl text-white lg:text-2xl">All recipes</h2>
                  <p className="text-xs text-white/50">{filteredEditRecipes.length} of {recipes.length} shown</p>
                </div>
                <button
                  type="button"
                  className="rounded-full bg-brand-accent px-3 py-1.5 text-xs font-medium text-brand-dark"
                  onClick={() => goToView('add')}
                >
                  + Add new
                </button>
              </div>

              <label className="mt-4 flex items-center gap-3 rounded-full border border-white/10 bg-brand-dark/50 px-4 py-2 text-sm text-white/80 focus-within:border-brand-accent">
                <span aria-hidden="true" className="text-white/40">🔍</span>
                <input
                  value={editSearch}
                  onChange={(event) => setEditSearch(event.target.value)}
                  placeholder="Search by name, slug, or ingredient…"
                  className="flex-1 border-none bg-transparent text-white outline-none placeholder:text-white/40"
                  aria-label="Search recipes"
                />
              </label>

              <div className="mt-5 max-h-72 space-y-2 overflow-auto rounded-2xl border border-white/10 bg-black/20 p-3 text-sm text-white/80">
                {filteredEditRecipes.map((recipe) => {
                  const isActive = recipe.slug === editSlug
                  return (
                    <button
                      key={recipe.slug}
                      type="button"
                      onClick={() => handleEditSelect(recipe.slug)}
                      className={`w-full rounded-xl border px-3 py-2 text-left transition ${isActive ? 'border-brand-accent bg-brand-accent/20 text-white' : 'border-white/10 bg-white/5 text-white/80 hover:border-brand-accent/60'}`}
                    >
                      <p className="font-medium text-white">{recipe.navn}</p>
                      <p className="text-xs text-white/50">Slug: {recipe.slug}</p>
                    </button>
                  )
                })}
                {filteredEditRecipes.length === 0 && (
                  <p className="text-xs text-white/60">{editSearch ? 'No recipes match that search.' : 'No recipes available yet.'}</p>
                )}
              </div>
            </section>

            <section className="rounded-panel bg-brand-dark/70 p-5 shadow-panel backdrop-blur lg:p-6">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="font-display text-xl text-white lg:text-2xl">{editSlug ? editName || 'Recipe' : 'Pick a recipe to edit'}</h2>
                  {editSlug && <p className="text-xs text-white/40">{editSlugInput}</p>}
                </div>
                <div className="flex items-center gap-2">
                  {editSlug && (
                    <button
                      type="button"
                      className="rounded-full border border-white/15 px-3 py-1.5 text-xs text-white/70 transition hover:text-white"
                      onClick={handleEditReset}
                    >
                      Reset
                    </button>
                  )}
                </div>
              </div>

              {editSlug ? (
                <div className="mt-4 space-y-4">
                  <div className="grid gap-4 md:grid-cols-2">
                    <label className="flex flex-col text-xs text-white/70">
                      <span className="mb-1 text-white/50">Name</span>
                      <input
                        value={editName}
                        onChange={(event) => setEditName(event.target.value)}
                        className="rounded-xl border border-white/10 bg-brand-surface/60 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                        placeholder="Recipe title"
                      />
                    </label>
                    <label className="flex flex-col text-xs text-white/70">
                      <span className="mb-1 text-white/50">Slug</span>
                      <div className="flex items-center gap-2">
                        <input
                          value={editSlugInput}
                          onChange={(event) => setEditSlugInput(event.target.value)}
                          className="flex-1 rounded-xl border border-white/10 bg-brand-surface/60 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                          placeholder="unique-slug"
                        />
                        <button
                          type="button"
                          className="rounded-full border border-white/20 px-3 py-1 text-xs text-white/70 transition hover:text-white"
                          onClick={slugFromName}
                        >
                          Auto
                        </button>
                      </div>
                    </label>
                    <label className="flex flex-col text-xs text-white/70">
                      <span className="mb-1 text-white/50">Servings (0 = freezer)</span>
                      <input
                        type="number"
                        min={0}
                        value={editServings}
                        onChange={(event) => setEditServings(Math.max(0, Number.parseInt(event.target.value, 10) || 0))}
                        className="rounded-xl border border-white/10 bg-brand-surface/60 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                      />
                    </label>
                    <label className="flex flex-col text-xs text-white/70">
                      <span className="mb-1 text-white/50">Placement</span>
                      <input
                        value={editPlacement}
                        onChange={(event) => setEditPlacement(event.target.value)}
                        className="rounded-xl border border-white/10 bg-brand-surface/60 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                        placeholder="Cookbook, page, or source"
                      />
                    </label>
                  </div>

                  <div className="flex flex-wrap items-center gap-4 text-xs text-white/70">
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={editIsBlacklisted} onChange={(event) => setEditIsBlacklisted(event.target.checked)} />
                      Blacklisted (hidden unless whitelisted)
                    </label>
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={editIsWhitelisted} onChange={(event) => setEditIsWhitelisted(event.target.checked)} />
                      Force include (even if blacklisted)
                    </label>
                  </div>

                  <div className="mt-6 space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className="font-display text-lg text-white">Ingredients</h3>
                      <button type="button" className="rounded-full border border-white/20 px-3 py-1 text-xs text-white/80 transition hover:text-white" onClick={addEditIngredientRow}>Add row</button>
                    </div>
                    <div className="space-y-3" onDragOver={allowDrop} onDrop={onDropToIngredients}>
                      {editIngredients.map((row) => (
                        <div
                          key={row.id}
                          className="grid gap-2 rounded-2xl border border-white/10 bg-white/5 p-4 text-xs text-white/80 sm:grid-cols-[minmax(0,1fr)_120px_100px_80px]"
                          draggable
                          onDragStart={(event) => {
                            event.dataTransfer.setData(DRAG_MIME, JSON.stringify({ id: row.id, source: 'ingredients' }))
                            event.dataTransfer.effectAllowed = 'move'
                          }}
                        >
                          <input
                            value={row.navn}
                            onChange={(event) => updateEditIngredientRow(row.id, { navn: event.target.value })}
                            placeholder="Ingredient"
                            className="rounded-lg border border-white/10 bg-brand-surface/50 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                          />
                          <input
                            value={row.amount}
                            onChange={(event) => updateEditIngredientRow(row.id, { amount: event.target.value })}
                            placeholder="Amount"
                            className="rounded-lg border border-white/10 bg-brand-surface/50 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                          />
                          <input
                            value={row.unit}
                            onChange={(event) => updateEditIngredientRow(row.id, { unit: event.target.value })}
                            placeholder="Unit"
                            className="rounded-lg border border-white/10 bg-brand-surface/50 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                          />
                          <button type="button" className="rounded-full border border-danger/40 px-3 py-2 text-danger transition hover:bg-danger/20" onClick={() => removeEditIngredientRow(row.id)}>Remove</button>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="mt-6 space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className="font-display text-lg text-white">Extras</h3>
                      <button type="button" className="rounded-full border border-white/20 px-3 py-1 text-xs text-white/80 transition hover:text-white" onClick={addEditExtraRow}>Add extra</button>
                    </div>
                    <div className="space-y-3" onDragOver={allowDrop} onDrop={onDropToExtras}>
                      {editExtras.length === 0 && <p className="text-xs text-white/60">Use extras for sides to purchase (e.g. salad, pita, toppings).</p>}
                      {editExtras.map((row) => (
                        <div
                          key={row.id}
                          className="grid gap-2 rounded-2xl border border-white/10 bg-white/5 p-4 text-xs text-white/80 sm:grid-cols-[minmax(0,1fr)_120px_100px_80px]"
                          draggable
                          onDragStart={(event) => {
                            event.dataTransfer.setData(DRAG_MIME, JSON.stringify({ id: row.id, source: 'extras' }))
                            event.dataTransfer.effectAllowed = 'move'
                          }}
                        >
                          <input
                            value={row.navn}
                            onChange={(event) => updateEditExtraRow(row.id, { navn: event.target.value })}
                            placeholder="Extra item"
                            className="rounded-lg border border-white/10 bg-brand-surface/50 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                          />
                          <input
                            value={row.amount}
                            onChange={(event) => updateEditExtraRow(row.id, { amount: event.target.value })}
                            placeholder="Amount"
                            className="rounded-lg border border-white/10 bg-brand-surface/50 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                          />
                          <input
                            value={row.unit}
                            onChange={(event) => updateEditExtraRow(row.id, { unit: event.target.value })}
                            placeholder="Unit"
                            className="rounded-lg border border-white/10 bg-brand-surface/50 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                          />
                          <button type="button" className="rounded-full border border-danger/40 px-3 py-2 text-danger transition hover:bg-danger/20" onClick={() => removeEditExtraRow(row.id)}>Remove</button>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="mt-6 space-y-2 text-xs text-white/70">
                    <h3 className="font-display text-lg text-white">Bulk rename</h3>
                    <div className="flex flex-wrap items-center gap-2">
                      <select
                        value={renameCandidate}
                        onChange={(event) => setRenameCandidate(event.target.value)}
                        className="min-w-[160px] flex-1 rounded-xl border border-white/10 bg-brand-surface/60 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                      >
                        {ingredientNames.length === 0 && <option value="">No ingredients yet</option>}
                        {ingredientNames.map((name) => (
                          <option key={name} value={name}>{name}</option>
                        ))}
                      </select>
                      <button
                        type="button"
                        className="rounded-full border border-white/20 px-3 py-2 text-xs text-white/80 transition hover:text-white"
                        onClick={() => openRenameTools()}
                      >
                        Open rename tools
                      </button>
                    </div>
                    <p className="text-white/50">Launches the ingredient rename helper with the selected name prefilled.</p>
                  </div>

                  {editStatus && (
                    <p className="rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-xs text-white/70">{editStatus}</p>
                  )}

                  <button
                    type="button"
                    className="w-full rounded-full bg-brand-accent px-5 py-3 text-brand-dark transition hover:translate-y-0.5"
                    onClick={handleEditSubmit}
                  >
                    Save changes
                  </button>
                </div>
              ) : (
                <p className="mt-6 text-sm text-white/60">Select a recipe from the list to start editing.</p>
              )}
            </section>
          </div>
        )}

        {view === 'config' && (
          <div className="space-y-6">
            <section className="rounded-panel bg-brand-surface/80 p-6 shadow-panel backdrop-blur">
              <div className="flex items-start justify-between gap-3">
                <div>
                  
                  <h2 className="font-display text-2xl text-white">Categories</h2>
                  <p className="mt-1 text-sm text-white/70">Manage ingredient categories and their priorities.</p>
                </div>
                <button
                  type="button"
                  className="text-xs uppercase tracking-[0.3em] text-white/60 transition hover:text-white"
                  onClick={fetchConfigData}
                  disabled={configLoading}
                >
                  Refresh
                </button>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-[minmax(0,280px)_120px_auto]">
                <input
                  value={newCategoryName}
                  onChange={(event) => setNewCategoryName(event.target.value)}
                  placeholder="New category"
                  className="rounded-xl border border-white/10 bg-brand-dark/40 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                />
                <input
                  type="number"
                  value={newCategoryPriority}
                  onChange={(event) => setNewCategoryPriority(event.target.value)}
                  placeholder="Priority"
                  className="rounded-xl border border-white/10 bg-brand-dark/40 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                />
                <button
                  type="button"
                  className="rounded-full bg-brand-accent px-4 py-2 text-sm text-brand-dark transition hover:translate-y-0.5 disabled:opacity-60"
                  onClick={handleCategoryCreate}
                  disabled={configLoading}
                >
                  Add category
                </button>
              </div>
              <div className="mt-4 space-y-2 text-sm text-white/80">
                {configCategories.length === 0 && <p className="text-xs text-white/60">No categories yet.</p>}
                {configCategories.map((category) => (
                  <div key={category.id} className="grid gap-2 rounded-2xl border border-white/10 bg-white/5 p-4 sm:grid-cols-[minmax(0,1fr)_120px_auto]">
                    <input
                      value={category.name}
                      onChange={(event) => updateCategoryDraft(category.id, { name: event.target.value })}
                      className="rounded-lg border border-white/10 bg-brand-surface/60 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                    />
                    <input
                      type="number"
                      value={category.priority}
                      onChange={(event) => updateCategoryDraft(category.id, { priority: Number.parseInt(event.target.value, 10) || 0 })}
                      className="rounded-lg border border-white/10 bg-brand-surface/60 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                    />
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        className="rounded-full border border-white/20 px-3 py-2 text-xs text-white/80 transition hover:text-white disabled:opacity-60"
                        onClick={() => handleCategorySave(category.id)}
                        disabled={configLoading}
                      >
                        Save
                      </button>
                      <button
                        type="button"
                        className="rounded-full border border-danger/40 px-3 py-2 text-xs text-danger transition hover:bg-danger/20 disabled:opacity-60"
                        onClick={() => handleCategoryDelete(category.id)}
                        disabled={configLoading}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-panel bg-brand-surface/80 p-6 shadow-panel backdrop-blur">
              <div className="flex items-start justify-between gap-3">
                <div>
                  
                  <h2 className="font-display text-2xl text-white">Ingredient mappings</h2>
                  <p className="mt-1 text-sm text-white/70">Map ingredient names to categories for shopping list grouping.</p>
                </div>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,200px)_auto]">
                <input
                  value={newIngredientName}
                  onChange={(event) => setNewIngredientName(event.target.value)}
                  placeholder="Ingredient name"
                  className="rounded-xl border border-white/10 bg-brand-dark/40 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                />
                <select
                  value={newIngredientCategory}
                  onChange={(event) => setNewIngredientCategory(event.target.value ? Number.parseInt(event.target.value, 10) : '')}
                  className="rounded-xl border border-white/10 bg-brand-dark/40 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                >
                  <option value="">Select category</option>
                  {configCategories.map((category) => (
                    <option key={category.id} value={category.id}>{category.name}</option>
                  ))}
                </select>
                <button
                  type="button"
                  className="rounded-full bg-brand-accent px-4 py-2 text-sm text-brand-dark transition hover:translate-y-0.5 disabled:opacity-60"
                  onClick={handleIngredientCreate}
                  disabled={configLoading}
                >
                  Add ingredient
                </button>
              </div>
              <div className="mt-4 space-y-2 text-sm text-white/80">
                {configItems.length === 0 && <p className="text-xs text-white/60">No ingredient mappings yet.</p>}
                {configItems.map((item) => (
                  <div key={item.id} className="grid gap-2 rounded-2xl border border-white/10 bg-white/5 p-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,200px)_auto]">
                    <input
                      value={item.name}
                      onChange={(event) => updateItemDraft(item.id, { name: event.target.value })}
                      className="rounded-lg border border-white/10 bg-brand-surface/60 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                    />
                    <select
                      value={item.category_id ?? ''}
                      onChange={(event) => updateItemDraft(item.id, { category_id: event.target.value ? Number.parseInt(event.target.value, 10) : null })}
                      className="rounded-lg border border-white/10 bg-brand-surface/60 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                    >
                      <option value="">Select category</option>
                      {configCategories.map((category) => (
                        <option key={category.id} value={category.id}>{category.name}</option>
                      ))}
                    </select>
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        className="rounded-full border border-white/20 px-3 py-2 text-xs text-white/80 transition hover:text-white disabled:opacity-60"
                        onClick={() => handleIngredientSave(item.id)}
                        disabled={configLoading}
                      >
                        Save
                      </button>
                      <button
                        type="button"
                        className="rounded-full border border-white/20 px-3 py-2 text-xs text-white/80 transition hover:text-white disabled:opacity-60"
                        onClick={() => openRenameTools(item.name)}
                      >
                        Rename
                      </button>
                      <button
                        type="button"
                        className="rounded-full border border-danger/40 px-3 py-2 text-xs text-danger transition hover:bg-danger/20 disabled:opacity-60"
                        onClick={() => handleIngredientDelete(item.id)}
                        disabled={configLoading}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-panel bg-brand-surface/80 p-6 shadow-panel backdrop-blur">
              <div className="flex items-start justify-between gap-3">
                <div>
                  
                  <h2 className="font-display text-2xl text-white">Staples</h2>
                  <p className="mt-1 text-sm text-white/70">Edit the always-buy staples list used during menu export.</p>
                </div>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-[minmax(0,1fr)_120px_120px_auto]">
                <input
                  value={newStapleName}
                  onChange={(event) => setNewStapleName(event.target.value)}
                  placeholder="Staple name"
                  className="rounded-xl border border-white/10 bg-brand-dark/40 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                />
                <input
                  value={newStapleAmount}
                  onChange={(event) => setNewStapleAmount(event.target.value)}
                  placeholder="Amount"
                  className="rounded-xl border border-white/10 bg-brand-dark/40 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                />
                <input
                  value={newStapleUnit}
                  onChange={(event) => setNewStapleUnit(event.target.value)}
                  placeholder="Unit"
                  className="rounded-xl border border-white/10 bg-brand-dark/40 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                />
                <button
                  type="button"
                  className="rounded-full bg-brand-accent px-4 py-2 text-sm text-brand-dark transition hover:translate-y-0.5 disabled:opacity-60"
                  onClick={handleStapleCreate}
                  disabled={configLoading}
                >
                  Add staple
                </button>
              </div>
              <div className="mt-4 space-y-2 text-sm text-white/80">
                {configStaples.length === 0 && <p className="text-xs text-white/60">No staples yet.</p>}
                {configStaples.map((staple) => (
                  <div key={staple.id} className="grid gap-2 rounded-2xl border border-white/10 bg-white/5 p-4 sm:grid-cols-[minmax(0,1fr)_120px_120px_auto]">
                    <input
                      value={staple.name}
                      onChange={(event) => updateStapleDraft(staple.id, { name: event.target.value })}
                      className="rounded-lg border border-white/10 bg-brand-surface/60 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                    />
                    <input
                      type="number"
                      step="0.1"
                      value={staple.amount}
                      onChange={(event) => updateStapleDraft(staple.id, { amount: Number.parseFloat(event.target.value) || 1 })}
                      className="rounded-lg border border-white/10 bg-brand-surface/60 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                    />
                    <input
                      value={staple.unit}
                      onChange={(event) => updateStapleDraft(staple.id, { unit: event.target.value })}
                      className="rounded-lg border border-white/10 bg-brand-surface/60 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                    />
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        className="rounded-full border border-white/20 px-3 py-2 text-xs text-white/80 transition hover:text-white disabled:opacity-60"
                        onClick={() => handleStapleSave(staple.id)}
                        disabled={configLoading}
                      >
                        Save
                      </button>
                      <button
                        type="button"
                        className="rounded-full border border-danger/40 px-3 py-2 text-xs text-danger transition hover:bg-danger/20 disabled:opacity-60"
                        onClick={() => handleStapleDelete(staple.id)}
                        disabled={configLoading}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-panel bg-brand-dark/70 p-6 shadow-panel backdrop-blur">
              <div className="flex items-start justify-between gap-3">
                <div>
                  
                  <h2 className="font-display text-2xl text-white">Staple label</h2>
                  <p className="mt-1 text-sm text-white/70">Choose which label appears above auto-added staples.</p>
                </div>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-[minmax(0,240px)_minmax(0,1fr)_auto]">
                <select
                  value={configStapleLabel}
                  onChange={(event) => setConfigStapleLabel(event.target.value)}
                  className="rounded-xl border border-white/10 bg-brand-surface/60 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                >
                  {configStapleOptions.map((option) => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </select>
                <input
                  value={customStapleLabel}
                  onChange={(event) => setCustomStapleLabel(event.target.value)}
                  placeholder="Custom label"
                  className="rounded-xl border border-white/10 bg-brand-surface/60 px-3 py-2 text-sm text-white outline-none focus:border-brand-accent"
                />
                <button
                  type="button"
                  className="rounded-full bg-brand-accent px-4 py-2 text-sm text-brand-dark transition hover:translate-y-0.5 disabled:opacity-60"
                  onClick={handleStapleLabelSave}
                  disabled={configLoading}
                >
                  Save label
                </button>
              </div>
            </section>

            {configStatus && (
              <p className="rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-xs text-white/70">{configStatus}</p>
            )}
          </div>
        )}

        {view === 'shopping' && (
          <div className="flex flex-col gap-5">
            {/* Action bar */}
            <section className="no-print rounded-panel bg-brand-surface/80 p-4 shadow-panel backdrop-blur lg:p-5">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <h2 className="font-display text-xl text-white lg:text-2xl">Ready to print</h2>
                  <p className="text-sm text-white/60">
                    {selectionEntries.length
                      ? `${selectionEntries.length} recipe${selectionEntries.length === 1 ? '' : 's'} on the menu`
                      : 'No recipes chosen yet.'}
                    {exporting && <span className="ml-2 text-brand-accent">Refreshing…</span>}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    className="rounded-full border border-white/15 bg-brand-dark/40 px-4 py-2 text-sm text-white/80 transition hover:text-white"
                    onClick={() => goToView('planner')}
                  >
                    ← Edit selection
                  </button>
                  <button
                    type="button"
                    className="rounded-full border border-white/15 bg-brand-dark/40 px-4 py-2 text-sm text-white/80 transition hover:text-white disabled:opacity-50"
                    onClick={() => window.print()}
                    disabled={!menuPreview}
                    title="Open the browser print dialog"
                  >
                    🖨 Print
                  </button>
                  <button
                    type="button"
                    className="inline-flex items-center gap-2 rounded-full bg-brand-accent px-5 py-2.5 text-sm font-semibold text-brand-dark transition hover:translate-y-[1px] disabled:opacity-50"
                    onClick={handleDownloadPdf}
                    disabled={!menuPreview || exporting}
                  >
                    ⬇ Save as PDF
                  </button>
                </div>
              </div>

              {/* Secondary actions, smaller and de-emphasized */}
              <details className="mt-3 text-xs text-white/50">
                <summary className="cursor-pointer select-none rounded-full px-2 py-1 hover:text-white">More export options</summary>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="rounded-full border border-white/15 px-3 py-1.5 text-white/80 transition hover:text-white disabled:opacity-50"
                    onClick={handleCopyMarkdown}
                    disabled={!menuMarkdown}
                  >
                    Copy markdown
                  </button>
                  <button
                    type="button"
                    className="rounded-full border border-white/15 px-3 py-1.5 text-white/80 transition hover:text-white disabled:opacity-50"
                    onClick={handleDownloadMarkdown}
                    disabled={!menuMarkdown}
                  >
                    Download .md
                  </button>
                  <button
                    type="button"
                    className="rounded-full border border-white/15 px-3 py-1.5 text-white/80 transition hover:text-white disabled:opacity-50"
                    onClick={() => void runGenerateMenu({ silent: false })}
                    disabled={!hasSelection || exporting}
                  >
                    Re-generate
                  </button>
                </div>
                {menuMarkdown && (
                  <details className="mt-3">
                    <summary className="cursor-pointer text-white/60 hover:text-white">View raw markdown</summary>
                    <pre className="mt-2 max-h-60 overflow-auto rounded-xl border border-white/10 bg-black/40 p-3 text-[11px] text-white/80">
                      {menuMarkdown}
                    </pre>
                  </details>
                )}
              </details>
            </section>

            {/* Preview */}
            <section className="rounded-panel bg-white/95 p-5 text-slate-900 shadow-panel lg:p-8">
              {!hasSelection ? (
                <div className="py-12 text-center text-sm text-slate-600">
                  <p>Add recipes on the Plan tab to see a printable preview here.</p>
                  <button
                    type="button"
                    className="mt-4 rounded-full bg-brand-dark px-4 py-2 text-sm font-medium text-white"
                    onClick={() => goToView('planner')}
                  >
                    Go to Plan →
                  </button>
                </div>
              ) : menuPreview ? (
                <div
                  ref={pdfPreviewRef}
                  className="shopping-pdf space-y-6 bg-white"
                >
                  <article dangerouslySetInnerHTML={{ __html: menuPreview.menuHtml }} />
                  {menuPreview.shoppingHtml && (
                    <article className="page-break" dangerouslySetInnerHTML={{ __html: menuPreview.shoppingHtml }} />
                  )}
                </div>
              ) : (
                <div className="py-10 text-center text-sm text-slate-600">
                  <div className="mx-auto mb-3 h-10 w-10 animate-spin rounded-full border-4 border-slate-300 border-t-slate-700" aria-label="Loading preview" />
                  Preparing your printable menu…
                </div>
              )}
            </section>
          </div>
        )}

        {view === 'tools' && (
          <section className="rounded-panel bg-brand-dark/70 p-5 shadow-panel backdrop-blur lg:p-6">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="font-display text-xl text-white lg:text-2xl">Bulk rename ingredients</h2>
                <p className="text-sm text-white/60">Fix inconsistent ingredient names across all recipes at once.</p>
              </div>
              <button
                type="button"
                className="rounded-full border border-white/15 px-3 py-1.5 text-xs text-white/70 transition hover:text-white"
                onClick={loadRecipes}
                title="Reload recipes from the server"
              >
                ↻ Refresh
              </button>
            </div>

            <form className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]" onSubmit={handleRenameSubmit}>
              <div className="space-y-3">
                <label className="block text-sm text-white/80">
                  <span className="mb-1 block text-xs uppercase tracking-[0.3em] text-white/50">From</span>
                  <input
                    value={renameFrom}
                    onChange={(event) => setRenameFrom(event.target.value)}
                    className="w-full rounded-xl border border-white/10 bg-brand-surface/60 px-3 py-2 text-white outline-none focus:border-brand-accent"
                    placeholder="e.g. Tomater"
                  />
                </label>
                <label className="block text-sm text-white/80">
                  <span className="mb-1 block text-xs uppercase tracking-[0.3em] text-white/50">To</span>
                  <input
                    value={renameTo}
                    onChange={(event) => setRenameTo(event.target.value)}
                    className="w-full rounded-xl border border-white/10 bg-brand-surface/60 px-3 py-2 text-white outline-none focus:border-brand-accent"
                    placeholder="e.g. Tomat"
                  />
                </label>
                <div className="space-y-2 text-xs text-white/70">
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={renameIncludeExtras}
                      onChange={(event) => setRenameIncludeExtras(event.target.checked)}
                    />
                    Also scan extras
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={renameCaseInsensitive}
                      onChange={(event) => setRenameCaseInsensitive(event.target.checked)}
                    />
                    Case insensitive match
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={renameForce}
                      onChange={(event) => setRenameForce(event.target.checked)}
                    />
                    Force merge when units differ (drops conflicting entry)
                  </label>
                </div>
                <button
                  type="submit"
                  className="w-full rounded-full bg-brand-accent px-5 py-2 text-brand-dark transition hover:translate-y-0.5 disabled:opacity-60"
                  disabled={renameSubmitting}
                >
                  {renameSubmitting ? 'Renaming…' : 'Rename ingredient'}
                </button>
              </div>
              <div className="rounded-2xl border border-white/10 bg-black/30 p-4 text-xs text-white/70">
                <p>
                  Results:
                  {renameResult ? <span className="ml-1 text-white/90">{renameResult}</span> : ' submit to view changes.'}
                </p>
                {renameConflicts && (
                  <pre className="mt-3 max-h-40 overflow-auto whitespace-pre-wrap rounded-lg border border-danger/30 bg-danger/10 p-3 text-[11px] text-danger-100">
                    {renameConflicts}
                  </pre>
                )}
                <p className="mt-4 text-white/50">
                  Tip: spin a new menu afterwards to refresh suggestions with updated ingredient names.
                </p>
              </div>
            </form>
          </section>
        )}

        <footer className="no-print mb-10 flex flex-wrap items-center justify-between gap-3 text-xs text-white/50">
          <span>
            API origin:{' '}
            <code className="rounded-full bg-black/30 px-2 py-1 text-[11px] text-white">{API_BASE || '(same host)'}</code>
          </span>
          <span>Frontend powered by Vite + React + Tailwind</span>
        </footer>
      </div>

      {/* Mobile bottom tab bar */}
      <nav
        className="no-print fixed inset-x-0 bottom-0 z-40 border-t border-white/10 bg-brand-dark/95 backdrop-blur lg:hidden"
        aria-label="Primary"
        style={{ paddingBottom: 'env(safe-area-inset-bottom, 0)' }}
      >
        <div className="mx-auto flex max-w-md items-stretch justify-around">
          {([
            { key: 'planner' as View, label: 'Plan', active: planActive, icon: '📋' },
            { key: 'edit' as View, label: 'Recipes', active: recipesActive, icon: '📖' },
            { key: 'config' as View, label: 'Settings', active: settingsActive, icon: '⚙️' },
          ]).map(({ key, label, active, icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => goToView(key)}
              aria-current={active ? 'page' : undefined}
              className={`flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] font-medium transition ${
                active ? 'text-brand-accent' : 'text-white/60 hover:text-white'
              }`}
            >
              <span aria-hidden="true" className="text-base leading-none">{icon}</span>
              <span>{label}</span>
            </button>
          ))}
        </div>
      </nav>
    </div>
  )
}

function SubTab({ label, active, onClick, disabled }: { label: string; active: boolean; onClick: () => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-current={active ? 'page' : undefined}
      className={`rounded-full px-4 py-1.5 font-medium transition ${
        active
          ? 'bg-brand-accent text-brand-dark shadow'
          : 'border border-white/10 bg-brand-dark/30 text-white/70 hover:text-white'
      } ${disabled ? 'cursor-not-allowed opacity-40' : ''}`}
    >
      {label}
    </button>
  )
}

export default App
