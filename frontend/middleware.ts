import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export function middleware(request: NextRequest) {
  const token = request.cookies.get('access_token')?.value
  const { pathname } = request.nextUrl

  // Public paths
  const isPublicPath = 
    pathname === '/login' || 
    pathname === '/register' || 
    pathname.startsWith('/auth')

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
     * - favicon.ico (favicon file)
     */
    '/((?!api|_next/static|_next/image|favicon.ico).*)',
  ],
}
