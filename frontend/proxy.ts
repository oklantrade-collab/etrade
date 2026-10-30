import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export function proxy(request: NextRequest) {
  const token = request.cookies.get('access_token')?.value
  const { pathname } = request.nextUrl

  // Public paths and static assets that must never be intercepted
  const isPublicPath = 
    pathname === '/login' || 
    pathname === '/register' || 
    pathname.startsWith('/auth') ||
    pathname.startsWith('/sounds') ||
    /\.(?:wav|mp3|ogg|ico|png|jpg|jpeg|svg|webp)$/i.test(pathname)

  // If path is root, redirect to dashboard or login
  if (pathname === '/') {
    if (token) return NextResponse.redirect(new URL('/portfolio', request.url))
    return NextResponse.redirect(new URL('/login', request.url))
  }

  // Redirect logic
  if (isPublicPath && token) {
    return NextResponse.redirect(new URL('/portfolio', request.url))
  }

  if (!isPublicPath && !token) {
    return NextResponse.redirect(new URL('/login', request.url))
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - api (API routes)
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - sounds (audio files: Thinkorswim bell, ding, chimes, etc.)
     * - favicon.ico (favicon file)
     * - static assets with extensions (.wav, .mp3, etc.)
     */
    '/((?!api|_next/static|_next/image|sounds|favicon.ico|.*\\.(?:wav|mp3|ogg|ico|png|jpg|jpeg|svg|webp)$).*)',
  ],
}
