import { useEffect, useMemo, useState } from 'react'
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
const TODAY_ISO = new Date().toISOString().slice(0, 10)

const DEFAULT_SIGNUP_FORM = {
  full_name: '',
  email: '',
  password: '',
}

const DEFAULT_LOGIN_FORM = {
  email: '',
  password: '',
}

const DEFAULT_PROFILE_FORM = {
  carrier_name: '',
  main_office_address: '',
  home_terminal_address: '',
  truck_trailer_numbers: '',
}

const DEFAULT_TRIP_FORM = {
  current_location: '',
  pickup_location: '',
  dropoff_location: '',
  current_cycle_used_hours: '0',
  start_date: TODAY_ISO,
}

function resolveApiUrl(path) {
  if (/^https?:\/\//.test(path)) {
    return path
  }
  if (!path.startsWith('/')) {
    return `${API_BASE_URL}/${path}`
  }
  return `${API_BASE_URL}${path}`
}

function isValidEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value || '').trim())
}

function toNumberOrZero(rawValue) {
  const parsed = Number.parseFloat(String(rawValue ?? '').trim())
  return Number.isFinite(parsed) ? parsed : 0
}

function formatHoursValue(value) {
  const numericValue = Number(value || 0)
  if (!Number.isFinite(numericValue)) {
    return '0 hr'
  }
  const rounded = Math.round(numericValue * 10) / 10
  return Number.isInteger(rounded) ? `${rounded.toFixed(0)} hr` : `${rounded.toFixed(1)} hr`
}

function compactDisplayLocation(value) {
  const text = String(value || '').trim()
  if (!text || text === 'EN ROUTE') {
    return text || 'En route'
  }

  const parts = text.split(',').map((part) => part.trim()).filter(Boolean)
  const filtered = parts.filter(
    (part) =>
      !/united states|usa/i.test(part) &&
      !/county|parish|borough|municipality|census area/i.test(part)
  )

  if (filtered.length >= 2) {
    return `${filtered[0]}, ${filtered[1]}`
  }
  return filtered[0] || parts[0] || text
}

function buildDayExecutionData(tripPlan) {
  if (!tripPlan?.daily_logs?.length) {
    return []
  }

  const stopsByDate = new Map()
  for (const stop of tripPlan.stops || []) {
    const dateKey = stop?.date || ''
    const currentStops = stopsByDate.get(dateKey) || []
    currentStops.push(stop)
    stopsByDate.set(dateKey, currentStops)
  }

  const cycleCap = Number(tripPlan.cycle_cap_hours || 0)
  let consumedCycleHours = Number(tripPlan.current_cycle_used_hours || 0)

  return tripPlan.daily_logs.map((day) => {
    const totalOnDutyHours = Number(day.driving_hours || 0) + Number(day.on_duty_hours || 0)
    consumedCycleHours += totalOnDutyHours
    const remainingCycleHours = Math.max(0, cycleCap - consumedCycleHours)
    const dayStops = stopsByDate.get(day.log_date) || []

    return {
      ...day,
      totalOnDutyHours,
      remainingCycleHours,
      stops: dayStops,
    }
  })
}

function SummaryCard({ label, value, helper }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">{label}</p>
      <p className="mt-2 text-base font-semibold text-slate-900">{value}</p>
      {helper ? <p className="mt-1 text-sm text-slate-500">{helper}</p> : null}
    </div>
  )
}

function ButtonSpinner() {
  return (
    <span
      className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent"
      aria-hidden="true"
    />
  )
}

function EditIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="h-4 w-4 fill-none stroke-current stroke-[1.8]">
      <path d="M11.7 4.3l4 4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4.5 15.5l2.8-.6 7.7-7.7a1.4 1.4 0 000-2l-.9-.9a1.4 1.4 0 00-2 0L4.4 12l-.6 2.8a.6.6 0 00.7.7z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function PlannerActionButtons({ tripPlan, tripPlanning, tripGenerating, onPlanTrip, onGenerateTrip }) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <button
        type="button"
        className={`${tripPlan ? 'btn-secondary' : 'btn-primary'} inline-flex w-full items-center justify-center gap-2 px-4 py-3`}
        disabled={tripPlanning}
        onClick={onPlanTrip}
      >
        {tripPlanning ? <ButtonSpinner /> : null}
        {tripPlanning ? 'Planning route...' : 'Plan route'}
      </button>
      <button
        type="button"
        className="btn-primary inline-flex w-full items-center justify-center gap-2 px-4 py-3"
        disabled={tripGenerating || !tripPlan}
        onClick={onGenerateTrip}
      >
        {tripGenerating ? <ButtonSpinner /> : null}
        {tripGenerating ? 'Generating logs...' : 'Generate logs'}
      </button>
    </div>
  )
}

function DayExecutionCard({ day }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Day {day.index}</p>
          <h3 className="mt-1 text-base font-semibold text-slate-900">{day.log_date}</h3>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className="metric-pill">
            <span className="metric-label">Miles</span>
            <span className="metric-value">{Math.round(day.miles_driven || 0)}</span>
          </span>
          <span className="metric-pill">
            <span className="metric-label">Driving</span>
            <span className="metric-value">{formatHoursValue(day.driving_hours)}</span>
          </span>
          <span className="metric-pill">
            <span className="metric-label">On Duty</span>
            <span className="metric-value">{formatHoursValue(day.totalOnDutyHours)}</span>
          </span>
          <span className="metric-pill">
            <span className="metric-label">Cycle Left</span>
            <span className="metric-value">{formatHoursValue(day.remainingCycleHours)}</span>
          </span>
        </div>
      </div>

      {day.stops?.length ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {day.stops.map((stop, index) => (
            <span key={`${stop.date}-${stop.time}-${index}`} className="rounded-full bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm">
              {stop.time} {stop.type}: {compactDisplayLocation(stop.location)}
            </span>
          ))}
        </div>
      ) : null}

      {day.notes?.length ? (
        <div className="mt-4 space-y-2">
          {day.notes.map((note, index) => (
            <p key={`${day.log_date}-note-${index}`} className="text-sm text-slate-600">
              {note}
            </p>
          ))}
        </div>
      ) : (
        <p className="mt-4 text-sm text-slate-500">Driving and rest were allocated within HOS limits for this day.</p>
      )}
    </div>
  )
}

function MapBoundsController({ geometry, locations }) {
  const map = useMap()

  useEffect(() => {
    const points = Array.isArray(geometry) ? geometry : []
    const bounds = []

    for (const point of points) {
      if (Array.isArray(point) && point.length >= 2) {
        bounds.push([point[0], point[1]])
      }
    }

    for (const key of ['current', 'pickup', 'dropoff']) {
      const location = locations?.[key]
      if (Number.isFinite(location?.lat) && Number.isFinite(location?.lon)) {
        bounds.push([location.lat, location.lon])
      }
    }

    if (bounds.length >= 2) {
      map.fitBounds(bounds, { padding: [28, 28] })
    } else if (bounds.length === 1) {
      map.setView(bounds[0], 8)
    }
  }, [geometry, locations, map])

  return null
}

function RouteMapPreview({ geometry, locations }) {
  const points = Array.isArray(geometry) ? geometry : []
  if (points.length < 2) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-5 text-sm text-slate-500">
        Route preview will appear here after planning.
      </div>
    )
  }

  const routePositions = points
    .filter((point) => Array.isArray(point) && point.length >= 2)
    .map(([lat, lon]) => [lat, lon])

  const locationDots = []
  if (Number.isFinite(locations?.current?.lat) && Number.isFinite(locations?.current?.lon)) {
    locationDots.push({ label: 'Start', lat: locations.current.lat, lon: locations.current.lon })
  }
  if (Number.isFinite(locations?.pickup?.lat) && Number.isFinite(locations?.pickup?.lon)) {
    locationDots.push({ label: 'Pickup', lat: locations.pickup.lat, lon: locations.pickup.lon })
  }
  if (Number.isFinite(locations?.dropoff?.lat) && Number.isFinite(locations?.dropoff?.lon)) {
    locationDots.push({ label: 'Dropoff', lat: locations.dropoff.lat, lon: locations.dropoff.lon })
  }

  return (
    <div className="route-live-map overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <MapContainer
        center={routePositions[0]}
        zoom={6}
        scrollWheelZoom={false}
        zoomControl={false}
        className="h-[280px] w-full sm:h-[340px]"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <MapBoundsController geometry={routePositions} locations={locations} />
        <Polyline positions={routePositions} pathOptions={{ color: '#111111', weight: 4, opacity: 0.9 }} />
        {locationDots.map((dot) => (
          <CircleMarker
            key={dot.label}
            center={[dot.lat, dot.lon]}
            radius={7}
            pathOptions={{ color: '#0f172a', weight: 2, fillColor: '#ffffff', fillOpacity: 1 }}
          >
            <Tooltip direction="top" offset={[0, -8]} permanent>
              {dot.label}
            </Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  )
}

function TextField({
  id,
  label,
  value,
  onChange,
  error,
  type = 'text',
  placeholder = '',
  autoComplete,
  multiline = false,
  rows = 3,
  min,
  max,
  step,
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-2 block text-sm font-medium text-slate-700">
        {label}
      </label>
      {multiline ? (
        <textarea
          id={id}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          autoComplete={autoComplete}
          rows={rows}
          className={error ? 'input-error' : ''}
        />
      ) : (
        <input
          id={id}
          type={type}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          autoComplete={autoComplete}
          min={min}
          max={max}
          step={step}
          className={error ? 'input-error' : ''}
        />
      )}
      {error ? <p className="field-error">{error}</p> : null}
    </div>
  )
}

function StepDots({ currentStep }) {
  const steps = ['Account', 'Profile', 'Planner']

  return (
    <div className="flex items-center gap-2">
      {steps.map((step, index) => {
        const stepNumber = index + 1
        const active = stepNumber === currentStep
        const complete = stepNumber < currentStep

        return (
          <div key={step} className="flex items-center gap-2">
            <div
              className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold ${
                active
                  ? 'bg-slate-950 text-white'
                  : complete
                    ? 'bg-emerald-100 text-emerald-700'
                    : 'bg-slate-100 text-slate-500'
              }`}
            >
              {stepNumber}
            </div>
            <span className={`hidden text-xs font-semibold uppercase tracking-[0.18em] sm:inline ${active ? 'text-slate-900' : 'text-slate-400'}`}>
              {step}
            </span>
            {index < steps.length - 1 ? <div className="h-px w-5 bg-slate-200 sm:w-10" /> : null}
          </div>
        )
      })}
    </div>
  )
}

function EmptyStateCard({ eyebrow, title, body, actionLabel, onAction }) {
  return (
    <div className="rounded-[24px] border border-dashed border-slate-300 bg-white p-5 shadow-sm">
      <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">{eyebrow}</p>
      <h3 className="mt-2 text-xl font-semibold text-slate-900">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-slate-500">{body}</p>
      {actionLabel ? (
        <button type="button" className="btn-secondary mt-5 w-full py-3" onClick={onAction}>
          {actionLabel}
        </button>
      ) : null}
    </div>
  )
}

function AuthPage({
  mode,
  onModeChange,
  signupForm,
  setSignupForm,
  loginForm,
  setLoginForm,
  signupErrors,
  loginErrors,
  showSignupErrors,
  showLoginErrors,
  onSignup,
  onLogin,
  authSubmitting,
  screenError,
}) {
  return (
    <main className="mx-auto flex min-h-screen max-w-[1440px] flex-col justify-center px-4 py-5 sm:px-6 sm:py-10 lg:px-10">
      <div className="grid items-center gap-6 lg:grid-cols-[1.05fr_0.95fr]">
        <section className="order-2 lg:order-1">
          <div className="max-w-[640px]">
            <p className="text-xs font-semibold uppercase tracking-[0.26em] text-slate-500">HOS Driver Log Platform</p>
            <h1 className="mt-4 text-4xl font-semibold leading-[1.05] text-slate-950 sm:text-5xl">
              Driver-first trip planning, without the clutter.
            </h1>
            <p className="mt-5 max-w-[560px] text-base leading-7 text-slate-600">
              Sign in, lock in your company defaults once, and generate route-ready driver logs from a workflow built for actual operations.
            </p>
          </div>

          <div className="mt-8 grid gap-4 sm:grid-cols-3">
            <div className="rounded-[24px] border border-slate-200 bg-white/90 p-5 shadow-[0_18px_50px_-36px_rgba(15,23,42,0.28)]">
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">01</p>
              <h2 className="mt-3 text-lg font-semibold text-slate-900">Authenticate</h2>
              <p className="mt-2 text-sm leading-6 text-slate-600">Create a driver account or return to your saved workspace.</p>
            </div>
            <div className="rounded-[24px] border border-slate-200 bg-white/90 p-5 shadow-[0_18px_50px_-36px_rgba(15,23,42,0.28)]">
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">02</p>
              <h2 className="mt-3 text-lg font-semibold text-slate-900">Onboard</h2>
              <p className="mt-2 text-sm leading-6 text-slate-600">Save carrier, terminal, and equipment defaults one time.</p>
            </div>
            <div className="rounded-[24px] border border-slate-200 bg-white/90 p-5 shadow-[0_18px_50px_-36px_rgba(15,23,42,0.28)]">
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">03</p>
              <h2 className="mt-3 text-lg font-semibold text-slate-900">Plan and Export</h2>
              <p className="mt-2 text-sm leading-6 text-slate-600">Review the route, generate the logs, and export the final PDF set.</p>
            </div>
          </div>

          <div className="mt-6 rounded-[28px] border border-slate-200 bg-white/75 p-5 shadow-[0_18px_50px_-36px_rgba(15,23,42,0.22)] backdrop-blur">
            <div className="flex flex-wrap gap-3">
              <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700">Route review before export</span>
              <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700">Locked onboarding defaults</span>
              <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700">PDF-ready output</span>
            </div>
          </div>
        </section>

        <section className="order-1 lg:order-2">
          <div className="mx-auto max-w-[520px] rounded-[32px] border border-slate-200 bg-white/96 p-5 shadow-[0_30px_90px_-40px_rgba(15,23,42,0.42)] backdrop-blur sm:p-7">
            <div className="mb-6 flex items-center justify-between">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">Secure Access</p>
                <h2 className="mt-2 text-2xl font-semibold text-slate-900">{mode === 'login' ? 'Sign in' : 'Create your driver account'}</h2>
              </div>
              <div className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-600">
                {mode === 'login' ? 'Returning driver' : 'New driver'}
              </div>
            </div>

            <div className="mb-6 grid grid-cols-2 gap-2 rounded-2xl bg-slate-100 p-1.5">
              <button
                type="button"
                className={`rounded-xl px-4 py-3 text-sm font-semibold transition ${
                  mode === 'login' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500'
                }`}
                onClick={() => onModeChange('login')}
              >
                Sign in
              </button>
              <button
                type="button"
                className={`rounded-xl px-4 py-3 text-sm font-semibold transition ${
                  mode === 'signup' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500'
                }`}
                onClick={() => onModeChange('signup')}
              >
                Sign up
              </button>
            </div>

            <p className="mb-6 text-sm leading-6 text-slate-500">
              {mode === 'login'
                ? 'Resume your saved driver profile and continue planning the next run.'
                : 'Create your account now and continue straight into driver onboarding.'}
            </p>

            {screenError ? (
              <div className="mb-6 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                {screenError}
              </div>
            ) : null}

            {mode === 'login' ? (
              <form className="space-y-6" onSubmit={onLogin}>
                <TextField
                  id="login-email"
                  label="Email"
                  type="email"
                  value={loginForm.email}
                  onChange={(event) => setLoginForm((current) => ({ ...current, email: event.target.value }))}
                  error={showLoginErrors ? loginErrors.email : ''}
                  autoComplete="email"
                />
                <TextField
                  id="login-password"
                  label="Password"
                  type="password"
                  value={loginForm.password}
                  onChange={(event) => setLoginForm((current) => ({ ...current, password: event.target.value }))}
                  error={showLoginErrors ? loginErrors.password : ''}
                  autoComplete="current-password"
                />
                <button type="submit" className="btn-primary mt-2 w-full py-3" disabled={authSubmitting}>
                  {authSubmitting ? 'Signing in...' : 'Sign in'}
                </button>
              </form>
            ) : (
              <form className="space-y-6" onSubmit={onSignup}>
                <TextField
                  id="signup-name"
                  label="Full name"
                  value={signupForm.full_name}
                  onChange={(event) => setSignupForm((current) => ({ ...current, full_name: event.target.value }))}
                  error={showSignupErrors ? signupErrors.full_name : ''}
                  autoComplete="name"
                />
                <TextField
                  id="signup-email"
                  label="Email"
                  type="email"
                  value={signupForm.email}
                  onChange={(event) => setSignupForm((current) => ({ ...current, email: event.target.value }))}
                  error={showSignupErrors ? signupErrors.email : ''}
                  autoComplete="email"
                />
                <TextField
                  id="signup-password"
                  label="Password"
                  type="password"
                  value={signupForm.password}
                  onChange={(event) => setSignupForm((current) => ({ ...current, password: event.target.value }))}
                  error={showSignupErrors ? signupErrors.password : ''}
                  autoComplete="new-password"
                />
                <button type="submit" className="btn-primary mt-2 w-full py-3" disabled={authSubmitting}>
                  {authSubmitting ? 'Creating account...' : 'Sign up'}
                </button>
              </form>
            )}
          </div>
        </section>
      </div>
    </main>
  )
}

function OnboardingPage({
  currentUser,
  profileForm,
  setProfileForm,
  profileErrors,
  showProfileErrors,
  onSubmit,
  profileSubmitting,
  screenError,
}) {
  return (
    <main className="mx-auto flex min-h-screen max-w-[1080px] items-start px-4 py-6 sm:px-6 sm:py-10 lg:items-center lg:px-10">
      <div className="w-full rounded-[28px] border border-slate-200 bg-white p-6 shadow-[0_24px_70px_-36px_rgba(15,23,42,0.35)] sm:rounded-[32px] sm:p-10 lg:p-12">
        <div className="mb-8">
          <StepDots currentStep={2} />
        </div>

        <div className="mb-10 flex flex-col gap-4 border-b border-slate-200 pb-8 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">Driver Onboarding</p>
            <h1 className="mt-3 text-3xl font-semibold text-slate-900">Complete your driver profile</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-500">
              These company and equipment defaults will be applied automatically to generated logs for {currentUser?.full_name}.
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
            <span className="block text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Cycle Policy</span>
            <span className="mt-1 block font-semibold text-slate-900">70-hour / 8-day</span>
          </div>
        </div>

        {screenError ? (
          <div className="mb-6 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {screenError}
          </div>
        ) : null}

        <form className="space-y-8" onSubmit={onSubmit}>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            <TextField
              id="carrier-name"
              label="Carrier name"
              value={profileForm.carrier_name}
              onChange={(event) => setProfileForm((current) => ({ ...current, carrier_name: event.target.value }))}
              error={showProfileErrors ? profileErrors.carrier_name : ''}
            />
            <TextField
              id="truck-trailer"
              label="Truck / trailer numbers"
              value={profileForm.truck_trailer_numbers}
              onChange={(event) =>
                setProfileForm((current) => ({ ...current, truck_trailer_numbers: event.target.value }))
              }
              error={showProfileErrors ? profileErrors.truck_trailer_numbers : ''}
            />
            <div className="sm:col-span-2">
              <TextField
                id="main-office"
                label="Main office address"
                value={profileForm.main_office_address}
                onChange={(event) =>
                  setProfileForm((current) => ({ ...current, main_office_address: event.target.value }))
                }
                error={showProfileErrors ? profileErrors.main_office_address : ''}
                multiline
                rows={3}
                placeholder="Street, city, state"
              />
            </div>
            <div className="sm:col-span-2">
              <TextField
                id="home-terminal"
                label="Home terminal address"
                value={profileForm.home_terminal_address}
                onChange={(event) =>
                  setProfileForm((current) => ({ ...current, home_terminal_address: event.target.value }))
                }
                error={showProfileErrors ? profileErrors.home_terminal_address : ''}
                multiline
                rows={3}
                placeholder="Street, city, state"
              />
            </div>
          </div>

          <div className="flex flex-col gap-4 border-t border-slate-200 pt-6 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-slate-500">You’ll review trip planning on the next screen.</p>
            <button type="submit" className="btn-primary w-full px-6 py-3 sm:w-auto" disabled={profileSubmitting}>
              {profileSubmitting ? 'Saving profile...' : 'Save and continue'}
            </button>
          </div>
        </form>
      </div>
    </main>
  )
}

function PlannerSection({
  tripForm,
  setTripForm,
  tripErrors,
  showTripErrors,
  onPlanTrip,
  onGenerateTrip,
  tripPlanning,
  tripGenerating,
  tripPlan,
}) {
  return (
    <section className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-[0_18px_50px_-36px_rgba(15,23,42,0.35)] sm:rounded-[28px] sm:p-6">
      <div className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">Trip Planner</p>
          <h2 className="mt-2 text-xl font-semibold text-slate-900 sm:text-2xl">Create a new trip</h2>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            Enter the trip inputs, plan the route first, then generate the daily log exports once the route looks right.
          </p>
        </div>
      </div>

      <form className="grid grid-cols-1 gap-5 sm:grid-cols-2" onSubmit={onPlanTrip}>
        <TextField
          id="current-location"
          label="Current location"
          value={tripForm.current_location}
          onChange={(event) => setTripForm((current) => ({ ...current, current_location: event.target.value }))}
          error={showTripErrors ? tripErrors.current_location : ''}
          placeholder="Phoenix, AZ"
        />
        <TextField
          id="pickup-location"
          label="Pickup location"
          value={tripForm.pickup_location}
          onChange={(event) => setTripForm((current) => ({ ...current, pickup_location: event.target.value }))}
          error={showTripErrors ? tripErrors.pickup_location : ''}
          placeholder="Flagstaff, AZ"
        />
        <TextField
          id="dropoff-location"
          label="Drop-off location"
          value={tripForm.dropoff_location}
          onChange={(event) => setTripForm((current) => ({ ...current, dropoff_location: event.target.value }))}
          error={showTripErrors ? tripErrors.dropoff_location : ''}
          placeholder="Dallas, TX"
        />
        <TextField
          id="cycle-used"
          label="Cycle hours already used"
          type="number"
          value={tripForm.current_cycle_used_hours}
          onChange={(event) =>
            setTripForm((current) => ({ ...current, current_cycle_used_hours: event.target.value }))
          }
          error={showTripErrors ? tripErrors.current_cycle_used_hours : ''}
          min="0"
          max="70"
          step="1"
        />
        <TextField
          id="start-date"
          label="Trip start date"
          type="date"
          value={tripForm.start_date}
          onChange={(event) => setTripForm((current) => ({ ...current, start_date: event.target.value }))}
          error={showTripErrors ? tripErrors.start_date : ''}
        />

        <div className="self-end">
          <PlannerActionButtons
            tripPlan={tripPlan}
            tripPlanning={tripPlanning}
            tripGenerating={tripGenerating}
            onPlanTrip={onPlanTrip}
            onGenerateTrip={onGenerateTrip}
          />
        </div>

        <div className="sm:col-span-2 rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Workflow</p>
          <p className="mt-2 text-sm font-semibold text-slate-900">1. Plan route</p>
          <p className="mt-1 text-sm text-slate-500">Review the route, stops, and trip days before generating the final log sheets.</p>
          <p className="mt-3 text-sm font-semibold text-slate-900">2. Generate logs</p>
          <p className="mt-1 text-sm text-slate-500">
            {tripPlan
              ? 'The route is ready. Generate the day-by-day SVG and PDF log exports.'
              : 'This becomes available after a route has been planned.'}
          </p>
        </div>
      </form>
    </section>
  )
}

function RouteSection({ tripPlan }) {
  const dayExecution = buildDayExecutionData(tripPlan)
  const finalCycleRemaining = dayExecution.length
    ? dayExecution[dayExecution.length - 1].remainingCycleHours
    : Math.max(0, Number(tripPlan?.cycle_cap_hours || 0) - Number(tripPlan?.current_cycle_used_hours || 0))

  return (
    <section className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-[0_18px_50px_-36px_rgba(15,23,42,0.35)] sm:rounded-[28px] sm:p-6">
      <div className="mb-5 flex flex-col gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">Route Overview</p>
          <h2 className="mt-2 text-xl font-semibold text-slate-900 sm:text-2xl">Planned route and stops</h2>
        </div>
        {tripPlan ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <SummaryCard label="Miles" value={Math.round(tripPlan.route?.total_distance_miles || 0)} />
            <SummaryCard label="Drive Time" value={`${tripPlan.route?.total_driving_hours || 0} hr`} />
            <SummaryCard label="Log Days" value={tripPlan.days_count || 0} />
            <SummaryCard label="Cycle Left After Trip" value={formatHoursValue(finalCycleRemaining)} />
          </div>
        ) : null}
      </div>

      {tripPlan ? (
        <div className="space-y-5">
          <RouteMapPreview geometry={tripPlan.route?.geometry} locations={tripPlan.locations} />

          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Daily Execution Plan</p>
                <p className="mt-2 text-sm text-slate-600">
                  Review how the trip is split across days, where operational stops land, and how many cycle hours remain after each day.
                </p>
              </div>
              {tripPlan.route?.openstreetmap_directions_url ? (
                <a
                  className="btn-secondary w-full justify-center px-4 py-2.5 text-center sm:w-auto"
                  href={tripPlan.route.openstreetmap_directions_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open directions
                </a>
              ) : null}
            </div>
          </div>

          {dayExecution.length ? (
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              {dayExecution.map((day) => (
                <DayExecutionCard key={`${day.log_date}-${day.index}`} day={day} />
              ))}
            </div>
          ) : null}

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
            <div className="space-y-3">
              {(tripPlan.route?.legs || []).map((leg) => (
                <div key={leg.index} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-slate-900">
                      {compactDisplayLocation(leg.from_location)} to {compactDisplayLocation(leg.to_location)}
                    </p>
                    <span className="text-xs text-slate-500">
                      {Math.round(leg.distance_miles)} mi • {leg.duration_hours} hr
                    </span>
                  </div>
                  {leg.instructions?.length ? <p className="mt-2 text-sm text-slate-600">{leg.instructions[0]}</p> : null}
                </div>
              ))}
            </div>

            <div className="space-y-3">
              {(tripPlan.stops || []).map((stop, index) => (
                <div key={`${stop.date}-${stop.time}-${index}`} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold capitalize text-slate-900">{stop.type}</p>
                    <span className="text-xs text-slate-500">
                      {stop.date} • {stop.time}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-slate-600">{stop.label}</p>
                  <p className="mt-1 text-xs text-slate-500">{compactDisplayLocation(stop.location)}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6 text-sm text-slate-500">
          Plan a route to view the map, trip legs, and scheduled stops.
        </div>
      )}
    </section>
  )
}

function ProfilePanel({
  profile,
  profileForm,
  setProfileForm,
  profileErrors,
  showProfileErrors,
  profileSubmitting,
  profileEditing,
  onStartEdit,
  onCancelEdit,
  onSaveProfile,
}) {
  return (
    <section className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-[0_18px_50px_-36px_rgba(15,23,42,0.35)] sm:rounded-[28px] sm:p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">Driver Profile</p>
          <h2 className="mt-2 text-xl font-semibold text-slate-900">Saved defaults</h2>
        </div>
        {profileEditing ? null : (
          <button
            type="button"
            className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-slate-50 text-slate-600 transition hover:border-slate-300 hover:bg-white hover:text-slate-900"
            onClick={onStartEdit}
            aria-label="Edit driver profile"
            title="Edit driver profile"
          >
            <EditIcon />
          </button>
        )}
      </div>

      {profileEditing ? (
        <form className="mt-5 space-y-4" onSubmit={onSaveProfile}>
          <TextField
            id="profile-carrier-name"
            label="Carrier name"
            value={profileForm.carrier_name}
            onChange={(event) => setProfileForm((current) => ({ ...current, carrier_name: event.target.value }))}
            error={showProfileErrors ? profileErrors.carrier_name : ''}
          />
          <TextField
            id="profile-main-office"
            label="Main office address"
            value={profileForm.main_office_address}
            onChange={(event) => setProfileForm((current) => ({ ...current, main_office_address: event.target.value }))}
            error={showProfileErrors ? profileErrors.main_office_address : ''}
            multiline
            rows={3}
          />
          <TextField
            id="profile-home-terminal"
            label="Home terminal address"
            value={profileForm.home_terminal_address}
            onChange={(event) =>
              setProfileForm((current) => ({ ...current, home_terminal_address: event.target.value }))
            }
            error={showProfileErrors ? profileErrors.home_terminal_address : ''}
            multiline
            rows={3}
          />
          <TextField
            id="profile-equipment"
            label="Truck / trailer numbers"
            value={profileForm.truck_trailer_numbers}
            onChange={(event) =>
              setProfileForm((current) => ({ ...current, truck_trailer_numbers: event.target.value }))
            }
            error={showProfileErrors ? profileErrors.truck_trailer_numbers : ''}
          />
          <div className="flex gap-3">
            <button type="submit" className="btn-primary inline-flex items-center justify-center gap-2 px-5 py-3" disabled={profileSubmitting}>
              {profileSubmitting ? <ButtonSpinner /> : null}
              {profileSubmitting ? 'Saving...' : 'Save'}
            </button>
            <button type="button" className="btn-secondary px-5 py-3" onClick={onCancelEdit} disabled={profileSubmitting}>
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <div className="mt-5 space-y-4">
          <SummaryCard label="Carrier" value={profile?.carrier_name || '—'} />
          <SummaryCard label="Main office" value={profile?.main_office_address || '—'} />
          <SummaryCard label="Home terminal" value={profile?.home_terminal_address || '—'} />
          <SummaryCard label="Equipment" value={profile?.truck_trailer_numbers || '—'} />
        </div>
      )}
    </section>
  )
}

function LogsPanel({ tripResult }) {
  return (
    <section className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-[0_18px_50px_-36px_rgba(15,23,42,0.35)] sm:rounded-[28px] sm:p-6">
      <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">Generated Logs</p>
      <h2 className="mt-2 text-xl font-semibold text-slate-900">Exports</h2>
      <div className="mt-5 space-y-3">
        {(tripResult?.generated_logs || []).length > 0 ? (
          tripResult.generated_logs.map((log) => (
            <div key={log.record_id || log.index} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-slate-900">
                    Day {log.index} • {log.log_date}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    {Math.round(log.miles_driven)} mi • {log.driving_hours} driving
                  </p>
                </div>
                <span
                  className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                    log.is_legal_today ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'
                  }`}
                >
                  {log.is_legal_today ? 'Compliant' : 'Review'}
                </span>
              </div>
              <div className="mt-4 flex flex-col gap-2 sm:flex-row">
                <a className="btn-ghost" href={resolveApiUrl(log.pdf_url)} target="_blank" rel="noreferrer">
                  PDF
                </a>
              </div>
            </div>
          ))
        ) : (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-5 text-sm text-slate-500">
            Generated log exports will appear here after you create a trip.
          </div>
        )}
      </div>
    </section>
  )
}

function HomePage({
  currentUser,
  profile,
  profileForm,
  setProfileForm,
  profileErrors,
  showProfileErrors,
  profileSubmitting,
  profileEditing,
  onStartProfileEdit,
  onCancelProfileEdit,
  onSaveProfile,
  tripForm,
  setTripForm,
  tripErrors,
  showTripErrors,
  onPlanTrip,
  onGenerateTrip,
  onLogout,
  tripPlanning,
  tripGenerating,
  tripPlan,
  tripResult,
  screenError,
  mobileHomeTab,
  setMobileHomeTab,
}) {
  return (
    <main className="mx-auto min-h-screen max-w-[1440px] px-4 py-5 pb-28 sm:px-6 sm:py-8 sm:pb-8 lg:px-10">
      <header className="mb-5 flex items-start justify-between rounded-[24px] border border-slate-200 bg-white px-5 py-4 shadow-[0_18px_50px_-36px_rgba(15,23,42,0.35)] sm:hidden">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">HOS Driver Log Platform</p>
          <h1 className="mt-2 text-xl font-semibold text-slate-900">{currentUser?.full_name}</h1>
          <p className="mt-1 text-sm text-slate-500">Driver dashboard</p>
        </div>
        <button type="button" className="btn-secondary px-4 py-2" onClick={onLogout}>
          Sign out
        </button>
      </header>

      <div className="mb-5 rounded-[24px] border border-slate-200 bg-slate-950 px-5 py-5 text-white shadow-[0_18px_50px_-36px_rgba(15,23,42,0.55)] sm:hidden">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Planning Status</p>
            <h2 className="mt-2 text-2xl font-semibold">Ready to plan the next run</h2>
            <p className="mt-2 text-sm leading-6 text-slate-300">
              Start with your route inputs, review the stops, then export the generated logs.
            </p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/10 px-4 py-3 text-right backdrop-blur">
            <span className="block text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-300">Cycle</span>
            <span className="mt-1 block text-sm font-semibold text-white">70 / 8</span>
          </div>
        </div>
      </div>

      <header className="mb-6 hidden flex-col gap-4 rounded-[24px] border border-slate-200 bg-white px-5 py-4 shadow-[0_18px_50px_-36px_rgba(15,23,42,0.35)] sm:mb-8 sm:flex sm:rounded-[28px] sm:px-6 sm:py-5 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">HOS Driver Log Platform</p>
          <h1 className="mt-2 text-2xl font-semibold text-slate-900">Good morning, {currentUser?.full_name}</h1>
          <p className="mt-1 text-sm text-slate-500">Plan trips, review route stops, and export daily logs.</p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="flex h-[42px] items-center rounded-xl border border-slate-200 bg-slate-50 px-4 text-sm font-semibold text-slate-700">
            70 hr / 8 day
          </div>
          <button type="button" className="btn-secondary h-[42px] w-full sm:w-auto" onClick={onLogout}>
            Sign out
          </button>
        </div>
      </header>

      {screenError ? (
        <div className="mb-6 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {screenError}
        </div>
      ) : null}

      <div className="space-y-5 lg:hidden">
        {mobileHomeTab === 'planner' ? (
          <PlannerSection
            tripForm={tripForm}
            setTripForm={setTripForm}
            tripErrors={tripErrors}
            showTripErrors={showTripErrors}
            onPlanTrip={onPlanTrip}
            onGenerateTrip={onGenerateTrip}
            tripPlanning={tripPlanning}
            tripGenerating={tripGenerating}
            tripPlan={tripPlan}
          />
        ) : null}
        {mobileHomeTab === 'route' ? (
          tripPlan ? (
            <RouteSection tripPlan={tripPlan} />
          ) : (
            <EmptyStateCard
              eyebrow="Route Overview"
              title="No route has been planned yet"
              body="Start in the planner tab to calculate the trip, stops, and driving days before reviewing the route."
              actionLabel="Go to planner"
              onAction={() => setMobileHomeTab('planner')}
            />
          )
        ) : null}
        {mobileHomeTab === 'logs' ? (
          tripResult ? (
            <div className="space-y-5">
              <ProfilePanel
                profile={profile}
                profileForm={profileForm}
                setProfileForm={setProfileForm}
                profileErrors={profileErrors}
                showProfileErrors={showProfileErrors}
                profileSubmitting={profileSubmitting}
                profileEditing={profileEditing}
                onStartEdit={onStartProfileEdit}
                onCancelEdit={onCancelProfileEdit}
                onSaveProfile={onSaveProfile}
              />
              <LogsPanel tripResult={tripResult} />
            </div>
          ) : (
            <div className="space-y-5">
              <ProfilePanel
                profile={profile}
                profileForm={profileForm}
                setProfileForm={setProfileForm}
                profileErrors={profileErrors}
                showProfileErrors={showProfileErrors}
                profileSubmitting={profileSubmitting}
                profileEditing={profileEditing}
                onStartEdit={onStartProfileEdit}
                onCancelEdit={onCancelProfileEdit}
                onSaveProfile={onSaveProfile}
              />
              <EmptyStateCard
                eyebrow="Log Exports"
                title="No generated logs yet"
                body="Generate the trip after planning to create day-by-day SVG and PDF exports for the run."
                actionLabel="Go to planner"
                onAction={() => setMobileHomeTab('planner')}
              />
            </div>
          )
        ) : null}
      </div>

      <div className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-200 bg-white/95 px-4 py-3 backdrop-blur sm:hidden">
        <div className="mx-auto grid max-w-[480px] grid-cols-3 gap-2 rounded-2xl bg-slate-100 p-1.5">
          {[
            ['planner', 'Plan'],
            ['route', 'Route'],
            ['logs', 'Exports'],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              className={`rounded-xl px-3 py-3 text-sm font-semibold transition ${
                mobileHomeTab === value ? 'bg-white text-slate-950 shadow-sm' : 'text-slate-500'
              }`}
              onClick={() => setMobileHomeTab(value)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="hidden grid-cols-1 gap-6 lg:grid lg:grid-cols-[minmax(0,1.5fr)_360px]">
        <section className="space-y-6">
          <PlannerSection
            tripForm={tripForm}
            setTripForm={setTripForm}
            tripErrors={tripErrors}
            showTripErrors={showTripErrors}
            onPlanTrip={onPlanTrip}
            onGenerateTrip={onGenerateTrip}
            tripPlanning={tripPlanning}
            tripGenerating={tripGenerating}
            tripPlan={tripPlan}
          />
          <RouteSection tripPlan={tripPlan} />
        </section>

        <aside className="space-y-6">
          <ProfilePanel
            profile={profile}
            profileForm={profileForm}
            setProfileForm={setProfileForm}
            profileErrors={profileErrors}
            showProfileErrors={showProfileErrors}
            profileSubmitting={profileSubmitting}
            profileEditing={profileEditing}
            onStartEdit={onStartProfileEdit}
            onCancelEdit={onCancelProfileEdit}
            onSaveProfile={onSaveProfile}
          />
          <LogsPanel tripResult={tripResult} />
        </aside>
      </div>
    </main>
  )
}

export default function App() {
  const [authLoading, setAuthLoading] = useState(true)
  const [authMode, setAuthMode] = useState('login')
  const [currentUser, setCurrentUser] = useState(null)
  const [profile, setProfile] = useState(null)
  const [onboardingRequired, setOnboardingRequired] = useState(true)
  const [screenError, setScreenError] = useState('')

  const [signupForm, setSignupForm] = useState(DEFAULT_SIGNUP_FORM)
  const [loginForm, setLoginForm] = useState(DEFAULT_LOGIN_FORM)
  const [authSubmitting, setAuthSubmitting] = useState(false)
  const [authAttempted, setAuthAttempted] = useState(false)

  const [profileForm, setProfileForm] = useState(DEFAULT_PROFILE_FORM)
  const [profileSubmitting, setProfileSubmitting] = useState(false)
  const [profileAttempted, setProfileAttempted] = useState(false)
  const [profileEditing, setProfileEditing] = useState(false)

  const [tripForm, setTripForm] = useState(DEFAULT_TRIP_FORM)
  const [tripPlan, setTripPlan] = useState(null)
  const [tripResult, setTripResult] = useState(null)
  const [tripPlanning, setTripPlanning] = useState(false)
  const [tripGenerating, setTripGenerating] = useState(false)
  const [tripAttempted, setTripAttempted] = useState(false)
  const [mobileHomeTab, setMobileHomeTab] = useState('planner')

  const signupErrors = useMemo(() => {
    const errors = {}
    if (!signupForm.full_name.trim()) {
      errors.full_name = 'Full name is required'
    }
    if (!isValidEmail(signupForm.email)) {
      errors.email = 'Enter a valid email'
    }
    if (String(signupForm.password || '').length < 8) {
      errors.password = 'Password must be at least 8 characters'
    }
    return errors
  }, [signupForm])

  const loginErrors = useMemo(() => {
    const errors = {}
    if (!isValidEmail(loginForm.email)) {
      errors.email = 'Enter a valid email'
    }
    if (!String(loginForm.password || '').trim()) {
      errors.password = 'Password is required'
    }
    return errors
  }, [loginForm])

  const profileErrors = useMemo(() => {
    const errors = {}
    if (!profileForm.carrier_name.trim()) {
      errors.carrier_name = 'Carrier name is required'
    }
    if (profileForm.main_office_address.trim().length < 5) {
      errors.main_office_address = 'Main office address is required'
    }
    if (profileForm.home_terminal_address.trim().length < 5) {
      errors.home_terminal_address = 'Home terminal address is required'
    }
    if (profileForm.truck_trailer_numbers.trim().length < 2) {
      errors.truck_trailer_numbers = 'Truck / trailer numbers are required'
    }
    return errors
  }, [profileForm])

  const tripErrors = useMemo(() => {
    const errors = {}
    if (!tripForm.current_location.trim()) {
      errors.current_location = 'Current location is required'
    }
    if (!tripForm.pickup_location.trim()) {
      errors.pickup_location = 'Pickup location is required'
    }
    if (!tripForm.dropoff_location.trim()) {
      errors.dropoff_location = 'Drop-off location is required'
    }

    const cycleUsed = Number.parseFloat(String(tripForm.current_cycle_used_hours || '').trim())
    if (!Number.isFinite(cycleUsed) || cycleUsed < 0 || cycleUsed > 70) {
      errors.current_cycle_used_hours = 'Use a value between 0 and 70'
    }

    if (!String(tripForm.start_date || '').trim()) {
      errors.start_date = 'Trip start date is required'
    }

    return errors
  }, [tripForm])

  async function apiFetch(path, options = {}) {
    const headers = {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    }

    const response = await fetch(`${API_BASE_URL}${path}`, {
      credentials: 'include',
      ...options,
      headers,
    })

    let payload = {}
    const contentType = response.headers.get('content-type') || ''
    if (contentType.includes('application/json')) {
      payload = await response.json()
    }

    if (!response.ok) {
      const message = payload.detail || `Request failed with status ${response.status}`
      const error = new Error(message)
      error.status = response.status
      error.payload = payload
      throw error
    }

    return payload
  }

  function applyAuthPayload(payload) {
    const nextUser = payload.user || null
    const nextProfile = payload.profile || null
    setCurrentUser(nextUser)
    setProfile(nextProfile)
    setOnboardingRequired(Boolean(payload.onboarding_required))

    if (nextProfile) {
      setProfileForm({
        carrier_name: nextProfile.carrier_name || '',
        main_office_address: nextProfile.main_office_address || '',
        home_terminal_address: nextProfile.home_terminal_address || '',
        truck_trailer_numbers: nextProfile.truck_trailer_numbers || '',
      })
    }
  }

  useEffect(() => {
    let active = true

    async function loadSession() {
      setAuthLoading(true)
      try {
        const payload = await apiFetch('/api/auth/me')
        if (!active) {
          return
        }
        applyAuthPayload(payload)
      } catch (error) {
        if (!active) {
          return
        }
        setCurrentUser(null)
        setProfile(null)
        setOnboardingRequired(true)
      } finally {
        if (active) {
          setAuthLoading(false)
        }
      }
    }

    loadSession()
    return () => {
      active = false
    }
  }, [])

  async function handleSignup(event) {
    event.preventDefault()
    setAuthAttempted(true)
    if (Object.keys(signupErrors).length > 0) {
      return
    }

    setAuthSubmitting(true)
    setScreenError('')
    try {
      const payload = await apiFetch('/api/auth/signup', {
        method: 'POST',
        body: JSON.stringify(signupForm),
      })
      applyAuthPayload(payload)
      setSignupForm(DEFAULT_SIGNUP_FORM)
      setTripPlan(null)
      setTripResult(null)
      setAuthAttempted(false)
    } catch (error) {
      setScreenError(error.message)
    } finally {
      setAuthSubmitting(false)
    }
  }

  async function handleLogin(event) {
    event.preventDefault()
    setAuthAttempted(true)
    if (Object.keys(loginErrors).length > 0) {
      return
    }

    setAuthSubmitting(true)
    setScreenError('')
    try {
      const payload = await apiFetch('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify(loginForm),
      })
      applyAuthPayload(payload)
      setLoginForm(DEFAULT_LOGIN_FORM)
      setTripPlan(null)
      setTripResult(null)
      setAuthAttempted(false)
    } catch (error) {
      setScreenError(error.message)
    } finally {
      setAuthSubmitting(false)
    }
  }

  async function handleLogout() {
    await apiFetch('/api/auth/logout', { method: 'POST' })
    setCurrentUser(null)
    setProfile(null)
    setOnboardingRequired(true)
    setTripPlan(null)
    setTripResult(null)
    setScreenError('')
    setAuthMode('login')
  }

  async function saveProfile() {
    setProfileAttempted(true)
    if (Object.keys(profileErrors).length > 0) {
      return false
    }

    setProfileSubmitting(true)
    setScreenError('')
    try {
      const payload = await apiFetch('/api/profile', {
        method: 'PUT',
        body: JSON.stringify(profileForm),
      })
      setProfile(payload.profile)
      setOnboardingRequired(false)
      setProfileAttempted(false)
      setProfileEditing(false)
      return true
    } catch (error) {
      setScreenError(error.message)
      return false
    } finally {
      setProfileSubmitting(false)
    }
  }

  async function handleProfileSubmit(event) {
    event.preventDefault()
    await saveProfile()
  }

  async function handleInlineProfileSave(event) {
    event.preventDefault()
    await saveProfile()
  }

  function syncProfileFormFromProfile(sourceProfile) {
    setProfileForm({
      carrier_name: sourceProfile?.carrier_name || '',
      main_office_address: sourceProfile?.main_office_address || '',
      home_terminal_address: sourceProfile?.home_terminal_address || '',
      truck_trailer_numbers: sourceProfile?.truck_trailer_numbers || '',
    })
  }

  function handleStartProfileEdit() {
    syncProfileFormFromProfile(profile)
    setProfileAttempted(false)
    setProfileEditing(true)
  }

  function handleCancelProfileEdit() {
    syncProfileFormFromProfile(profile)
    setProfileAttempted(false)
    setProfileEditing(false)
  }

  const tripPayload = useMemo(
    () => ({
      current_location: tripForm.current_location.trim(),
      pickup_location: tripForm.pickup_location.trim(),
      dropoff_location: tripForm.dropoff_location.trim(),
      current_cycle_used_hours: toNumberOrZero(tripForm.current_cycle_used_hours),
      start_date: tripForm.start_date,
    }),
    [tripForm]
  )

  async function handlePlanTrip(event) {
    event.preventDefault()
    setTripAttempted(true)
    if (Object.keys(tripErrors).length > 0) {
      return
    }

    setTripPlanning(true)
    setScreenError('')
    try {
      const payload = await apiFetch('/api/trips/plan', {
        method: 'POST',
        body: JSON.stringify(tripPayload),
      })
      setTripPlan(payload)
      setTripResult(null)
      setMobileHomeTab('route')
    } catch (error) {
      setScreenError(error.message)
    } finally {
      setTripPlanning(false)
    }
  }

  async function handleGenerateTrip() {
    setTripAttempted(true)
    if (Object.keys(tripErrors).length > 0) {
      return
    }

    setTripGenerating(true)
    setScreenError('')
    try {
      const payload = await apiFetch('/api/trips/generate', {
        method: 'POST',
        body: JSON.stringify(tripPayload),
      })
      setTripPlan(payload.plan || null)
      setTripResult(payload)
      setMobileHomeTab('logs')
    } catch (error) {
      setScreenError(error.message)
    } finally {
      setTripGenerating(false)
    }
  }

  if (authLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center px-6">
        <div className="rounded-3xl border border-slate-200 bg-white px-8 py-6 text-sm text-slate-500 shadow-sm">
          Loading workspace...
        </div>
      </main>
    )
  }

  if (!currentUser) {
    return (
      <AuthPage
        mode={authMode}
        onModeChange={(nextMode) => {
          setScreenError('')
          setAuthAttempted(false)
          setAuthMode(nextMode)
        }}
        signupForm={signupForm}
        setSignupForm={setSignupForm}
        loginForm={loginForm}
        setLoginForm={setLoginForm}
        signupErrors={signupErrors}
        loginErrors={loginErrors}
        showSignupErrors={authAttempted && authMode === 'signup'}
        showLoginErrors={authAttempted && authMode === 'login'}
        onSignup={handleSignup}
        onLogin={handleLogin}
        authSubmitting={authSubmitting}
        screenError={screenError}
      />
    )
  }

  if (onboardingRequired) {
    return (
      <OnboardingPage
        currentUser={currentUser}
        profileForm={profileForm}
        setProfileForm={setProfileForm}
        profileErrors={profileErrors}
        showProfileErrors={profileAttempted}
        onSubmit={handleProfileSubmit}
        profileSubmitting={profileSubmitting}
        screenError={screenError}
      />
    )
  }

  return (
    <HomePage
      currentUser={currentUser}
      profile={profile}
      profileForm={profileForm}
      setProfileForm={setProfileForm}
      profileErrors={profileErrors}
      showProfileErrors={profileAttempted}
      profileSubmitting={profileSubmitting}
      profileEditing={profileEditing}
      onStartProfileEdit={handleStartProfileEdit}
      onCancelProfileEdit={handleCancelProfileEdit}
      onSaveProfile={handleInlineProfileSave}
      tripForm={tripForm}
      setTripForm={setTripForm}
      tripErrors={tripErrors}
      showTripErrors={tripAttempted}
      onPlanTrip={handlePlanTrip}
      onGenerateTrip={handleGenerateTrip}
      onLogout={handleLogout}
      tripPlanning={tripPlanning}
      tripGenerating={tripGenerating}
      tripPlan={tripPlan}
      tripResult={tripResult}
      screenError={screenError}
      mobileHomeTab={mobileHomeTab}
      setMobileHomeTab={setMobileHomeTab}
    />
  )
}
