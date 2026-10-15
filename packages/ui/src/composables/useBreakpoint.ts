import { useMediaQuery } from '@vueuse/core'

const MOBILE_BREAKPOINT = '(max-width: 767px)'
const TABLET_BREAKPOINT = '(min-width: 768px) and (max-width: 1023px)'
const DESKTOP_BREAKPOINT = '(min-width: 1024px)'

export function useBreakpoint() {
  const isMobile = useMediaQuery(MOBILE_BREAKPOINT)
  const isTablet = useMediaQuery(TABLET_BREAKPOINT)
  const isDesktop = useMediaQuery(DESKTOP_BREAKPOINT)
  return { isMobile, isTablet, isDesktop }
}
