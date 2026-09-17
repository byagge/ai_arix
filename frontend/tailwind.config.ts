import type { Config } from 'tailwindcss';

/**
 * Arix console — otris / OpenAI-panel tokens.
 * Greyscale surfaces + ChatGPT green accent.
 */
const config: Config = {
  darkMode: 'class',
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    colors: {
      transparent: 'transparent',
      current: 'currentColor',
      white: '#ffffff',
      black: '#000000',
      bg: {
        DEFAULT: 'var(--bg)',
        rail: 'var(--bg-rail)',
        elevated: 'var(--bg-elevated)',
        input: 'var(--bg-input)',
        hover: 'var(--bg-hover)',
        active: 'var(--bg-active)',
        accent: 'var(--bg-accent)',
        surface3: 'var(--bg-surface-3)',
      },
      fg: {
        DEFAULT: 'var(--fg)',
        secondary: 'var(--fg-secondary)',
        tertiary: 'var(--fg-tertiary)',
        muted: 'var(--fg-muted)',
        inverted: 'var(--fg-inverted)',
      },
      border: {
        DEFAULT: 'var(--border)',
        soft: 'var(--border-soft)',
        strong: 'var(--border-strong)',
      },
      accent: {
        DEFAULT: 'var(--accent)',
        hover: 'var(--accent-2)',
        soft: 'var(--accent-soft)',
      },
      danger: 'var(--danger)',
      warn: 'var(--warn)',
      blue: 'var(--blue)',
      amber: {
        bg: 'var(--amber-bg)',
        line: 'var(--amber-line)',
        btn: 'var(--amber-btn)',
        text: 'var(--amber-text)',
      },
    },
    extend: {
      fontFamily: {
        sans: ['var(--font-sans)'],
        mono: ['var(--font-mono)'],
      },
      borderRadius: {
        DEFAULT: '8px',
        sm: '6px',
        lg: '12px',
        xl: '12px',
        '2xl': '16px',
      },
      spacing: {
        rail: '232px',
      },
      maxWidth: {
        console: '1180px',
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(3px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.15' },
        },
      },
      animation: {
        'fade-in': 'fade-in 180ms ease',
        blink: 'blink 1.05s steps(2, start) infinite',
      },
      boxShadow: {
        menu: '0 16px 40px rgba(0,0,0,0.55)',
        modal: '0 28px 70px rgba(0,0,0,0.65)',
      },
    },
  },
  plugins: [],
};

export default config;
