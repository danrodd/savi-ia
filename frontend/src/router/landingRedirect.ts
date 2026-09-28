/**
 * Con la landing activa, quien entra a la raíz sin sesión ve la landing en
 * vez del login. Con sesión, la raíz sigue siendo el chat; y en el servidor
 * de un cliente (landing apagada) la raíz sigue llevando al login.
 *
 * Solo la raíz: un link a una conversación (`/c/:id`) sin sesión sigue yendo
 * al login, que después devuelve a esa conversación.
 */
export function shouldShowLanding(
  routeName: string | symbol | null | undefined,
  isAuthenticated: boolean,
  landingEnabled: boolean,
): boolean {
  return landingEnabled && !isAuthenticated && routeName === 'home'
}
