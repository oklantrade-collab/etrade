import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  // Permitir imágenes de dominios externos

  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: '**.supabase.co',
      },
      {
        protocol: 'https',
        hostname: 'cdn.supabase.co',
      }
    ],
  },

  // Variables de entorno públicas
  env: {
    NEXT_PUBLIC_APP_VERSION: '4.5.0',
    NEXT_PUBLIC_APP_NAME: 'eTrader v4',
  },

  // Rewrites para proxy al backend
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080'
    return [
      {
        source: '/api/v1/:path*',
        destination: `${apiUrl}/api/v1/:path*`,
      },
      // Soporte para forex
      {
        source: '/api/v1/forex/:path*',
        destination: `${apiUrl}/api/v1/forex/:path*`,
      },
      // Soporte para stocks (bolsa)
      {
        source: '/api/v1/stocks/:path*',
        destination: `${apiUrl}/api/v1/stocks/:path*`,
      }
    ]
  },

  // Redirect de / a /dashboard y manejo de portafolio
  async redirects() {
    return [
      {
        source: '/',
        destination: '/dashboard',
        permanent: false,
      },
      {
        source: '/portafolio',
        destination: '/portfolio',
        permanent: true,
      }
    ]
  },

  // Headers de seguridad
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
        ],
      },
    ]
  },
}

export default nextConfig
