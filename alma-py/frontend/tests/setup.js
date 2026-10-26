import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach } from 'vitest'
import { cleanup } from '@testing-library/react'
import { setSession } from '../src/lib'

class RO { observe() {} unobserve() {} disconnect() {} }
globalThis.ResizeObserver = RO
window.ResizeObserver = RO
window.matchMedia = window.matchMedia || (() => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} }))
window.scrollTo = () => {}
window.__ALMA_API__ = process.env.ALMA_TEST_API || 'http://127.0.0.1:8000'
navigator.clipboard = navigator.clipboard || { writeText: async () => {} }
beforeEach(() => { setSession(null); window.location.hash = '#/' })
afterEach(() => cleanup())
