import { createTheme, lightThemePrimitives } from 'baseui'

// Base Web theme tuned toward Uber's Base look: black primary, clean neutral.
export const theme = createTheme(
  {
    ...lightThemePrimitives,
    primary: '#000000',
    primary50: '#f6f6f6',
    primary100: '#eeeeee',
    primary200: '#dddddd',
    primary300: '#cccccc',
    primary400: '#888888',
    primary500: '#000000',
    primary600: '#000000',
    primary700: '#000000',
  },
  {
    colors: {
      buttonPrimaryFill: '#000000',
      buttonPrimaryHover: '#333333',
      buttonPrimaryActive: '#1f1f1f',
      buttonPrimaryText: '#ffffff',
      borderAccent: '#000000',
    },
  },
)
