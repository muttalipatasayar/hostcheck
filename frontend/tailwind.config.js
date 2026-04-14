/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: '#f0f2f7',
          lowest:  '#eaedf5',
          low:     '#ffffff',
          high:    '#f2f4fa',
          highest: '#e8eaf3',
          variant: '#f0f2f8',
        },
        primary: {
          DEFAULT:   '#3b7eff',
          container: '#2563eb',
          fixed:     '#dbeafe',
          'fixed-dim': '#3b7eff',
          on:        '#ffffff',
        },
        secondary: {
          DEFAULT:   '#4a6cf7',
          container: '#1e40af',
          on:        '#ffffff',
        },
        tertiary: {
          DEFAULT:   '#f59e0b',
          container: '#fef3c7',
          on:        '#78350f',
        },
        error: {
          DEFAULT:   '#ef4444',
          container: '#fee2e2',
          on:        '#7f1d1d',
        },
        'on-surface': {
          DEFAULT: '#1a1d2e',
          variant: '#4a5068',
        },
        outline: {
          DEFAULT: '#6b7388',
          variant: '#9da5be',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      fontSize: {
        'display-md':   ['2.75rem', { lineHeight:'1.2',  letterSpacing:'-0.02em' }],
        'headline-lg':  ['2rem',    { lineHeight:'1.25', letterSpacing:'-0.015em' }],
        'headline-md':  ['1.75rem', { lineHeight:'1.3',  letterSpacing:'-0.01em' }],
        'title-lg':     ['1.375rem',{ lineHeight:'1.4' }],
        'title-md':     ['1rem',    { lineHeight:'1.5',  fontWeight:'500' }],
        'body-md':      ['0.875rem',{ lineHeight:'1.5' }],
        'body-sm':      ['0.8125rem',{lineHeight:'1.5' }],
        'label-md':     ['0.75rem', { lineHeight:'1.4',  letterSpacing:'0.01em' }],
        'label-sm':     ['0.6875rem',{lineHeight:'1.4',  letterSpacing:'0.01em' }],
      },
      borderRadius: {
        'btn':  '0.375rem',
        'card': '0.75rem',
        'xl':   '1rem',
        '2xl':  '1.5rem',
      },
      boxShadow: {
        'ambient':       '0 2px 16px rgba(0,6,30,0.06)',
        'ambient-lg':    '0 8px 32px rgba(0,6,30,0.08)',
        'primary-glow':  '0 0 12px rgba(59,127,255,0.25)',
        'float':         '0 8px 32px rgba(0,6,30,0.10)',
        'card':          '0 1px 4px rgba(0,6,30,0.07)',
      },
      backdropBlur: { glass: '24px' },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4,0,0.6,1) infinite',
        'fade-in':    'fadeIn 0.2s ease-out',
        'slide-up':   'slideUp 0.25s ease-out',
        'glow-pulse': 'glowPulse 2s ease-in-out infinite',
      },
      keyframes: {
        fadeIn:    { '0%':{ opacity:'0' },           '100%':{ opacity:'1' } },
        slideUp:   { '0%':{ opacity:'0', transform:'translateY(8px)' }, '100%':{ opacity:'1', transform:'translateY(0)' } },
        glowPulse: { '0%,100%':{ opacity:'1' },      '50%':{ opacity:'0.4' } },
      },
      spacing: { '18':'4.5rem', '22':'5.5rem' },
    },
  },
  plugins: [],
}
