/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Surface hierarchy — "Atmospheric Precision" palette
        surface: {
          DEFAULT: '#111317',
          lowest: '#0d0f12',
          low: '#1a1c20',
          high: '#282a2e',
          highest: '#333539',
          variant: '#1e2128',
        },
        // Primary
        primary: {
          DEFAULT: '#adc6ff',
          container: '#4d8eff',
          fixed: '#d8e2ff',
          'fixed-dim': '#adc6ff',
          on: '#002e6a',
        },
        // Secondary
        secondary: {
          DEFAULT: '#b1c6f9',
          container: '#2a4a8a',
          on: '#001a42',
        },
        // Tertiary (Warning)
        tertiary: {
          DEFAULT: '#ffb786',
          container: '#8a4000',
          on: '#3e1500',
        },
        // Error (Critical)
        error: {
          DEFAULT: '#ffb4ab',
          container: '#8c1d18',
          on: '#410002',
        },
        // On-surface tokens
        'on-surface': {
          DEFAULT: '#e3e5ef',
          variant: '#c2c6d6',
        },
        // Outline
        outline: {
          DEFAULT: '#8d9099',
          variant: '#424754',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      fontSize: {
        'display-md': ['2.75rem', { lineHeight: '1.2', letterSpacing: '-0.02em' }],
        'headline-lg': ['2rem', { lineHeight: '1.25', letterSpacing: '-0.015em' }],
        'headline-md': ['1.75rem', { lineHeight: '1.3', letterSpacing: '-0.01em' }],
        'title-lg': ['1.375rem', { lineHeight: '1.4' }],
        'title-md': ['1rem', { lineHeight: '1.5', fontWeight: '500' }],
        'body-md': ['0.875rem', { lineHeight: '1.5' }],
        'body-sm': ['0.8125rem', { lineHeight: '1.5' }],
        'label-md': ['0.75rem', { lineHeight: '1.4', letterSpacing: '0.01em' }],
        'label-sm': ['0.6875rem', { lineHeight: '1.4', letterSpacing: '0.01em' }],
      },
      borderRadius: {
        'btn': '0.375rem',
        'card': '0.75rem',
        'xl': '1rem',
        '2xl': '1.5rem',
      },
      boxShadow: {
        'ambient': '0 8px 32px rgba(0, 20, 80, 0.06)',
        'ambient-lg': '0 16px 64px rgba(0, 20, 80, 0.08)',
        'primary-glow': '0 0 12px rgba(173, 198, 255, 0.3)',
        'float': '0 24px 64px rgba(0, 10, 40, 0.12)',
      },
      backdropBlur: {
        'glass': '24px',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in': 'fadeIn 0.2s ease-out',
        'slide-up': 'slideUp 0.25s ease-out',
        'glow-pulse': 'glowPulse 2s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        glowPulse: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        }
      },
      spacing: {
        '18': '4.5rem',
        '22': '5.5rem',
      }
    },
  },
  plugins: [],
}
