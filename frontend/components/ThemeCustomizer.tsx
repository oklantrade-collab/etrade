'use client'
import { useEffect, useState } from 'react'

export default function ThemeCustomizer() {
  const [theme, setTheme] = useState<any>({
    bgColor: '#0a0e17',
    bgImage: '',
    titleFont: 'Inter',
    headerFont: 'Inter',
    contentFont: 'Inter',
    contentColor: '#e2e8f0'
  })

  useEffect(() => {
    // Load theme from localStorage
    const savedTheme = localStorage.getItem('app_theme_custom')
    if (savedTheme) {
      try {
        setTheme((prev: any) => ({ ...prev, ...JSON.parse(savedTheme) }))
      } catch (e) {
        console.error("Failed to parse theme", e)
      }
    }

    // Listen for theme changes (custom event)
    const handleThemeChange = () => {
      const updatedTheme = localStorage.getItem('app_theme_custom')
      if (updatedTheme) {
        setTheme(JSON.parse(updatedTheme))
      }
    }

    window.addEventListener('themeUpdated', handleThemeChange)
    return () => window.removeEventListener('themeUpdated', handleThemeChange)
  }, [])

    const isLight = (color: string) => {
      if (!color || color === 'transparent') return false;
      const hex = color.replace('#', '');
      const r = parseInt(hex.substring(0, 2), 16);
      const g = parseInt(hex.substring(2, 4), 16);
      const b = parseInt(hex.substring(4, 6), 16);
      const brightness = (r * 299 + g * 587 + b * 114) / 1000;
      return brightness > 128;
    }

    const lightMode = isLight(theme.bgColor);
    const primaryText = theme.contentColor || (lightMode ? '#0f172a' : '#e2e8f0');
    const secondaryText = lightMode ? '#334155' : '#94a3b8';
    const mutedText = lightMode ? '#475569' : '#64748b';

    const css = `
    :root {
      --bg-primary: ${theme.bgColor || '#0a0e17'} !important;
      --bg-secondary: ${theme.bgColor ? theme.bgColor + 'dd' : '#111827'} !important;
      --bg-card: ${theme.bgColor ? theme.bgColor + 'ee' : '#1a1f2e'} !important;
      --text-primary: ${primaryText} !important;
      --text-secondary: ${secondaryText} !important;
      --text-muted: ${mutedText} !important;
      --border-color: ${lightMode ? 'rgba(0,0,0,0.15)' : 'rgba(255,255,255,0.1)'} !important;
    }

    body {
      ${theme.bgImage ? `background-image: url("${theme.bgImage}") !important;` : ''}
      ${theme.bgImage ? `background-size: cover !important;` : ''}
      ${theme.bgImage ? `background-attachment: fixed !important; background-position: center !important;` : ''}
      ${theme.contentFont ? `font-family: ${theme.contentFont}, Inter, sans-serif !important;` : ''}
      background-color: var(--bg-primary) !important;
      color: var(--text-primary) !important;
    }

    h1, h2, h3, h4, h5, h6, .card-value, .sidebar-logo h1 {
      ${theme.titleFont ? `font-family: ${theme.titleFont}, Inter, sans-serif !important;` : ''}
      color: var(--text-primary) !important;
    }

    thead th, .card-title, .sidebar-nav .nav-link, table th {
      ${theme.headerFont ? `font-family: ${theme.headerFont}, Inter, sans-serif !important;` : ''}
      color: var(--text-secondary) !important;
    }

    .main-content, .card, .sidebar, .table-container, .log-terminal {
      background-color: var(--bg-card) !important;
      color: var(--text-primary) !important;
    }

    .sidebar .nav-link:hover, .btn-ghost:hover {
        background-color: ${lightMode ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.05)'} !important;
    }

    span, div, p, label, input, select {
        ${theme.contentFont ? `font-family: ${theme.contentFont}, Inter, sans-serif;` : ''}
    }
  `

  return <style dangerouslySetInnerHTML={{ __html: css }} />
}
