import messages from '../src/messages/en.json';
import type { Preview } from '@storybook/nextjs-vite';
import React, { useEffect } from 'react';
import '../src/app/globals.css';
import { PreviewProvider } from '../src/lib/api/services/preview-provider.client';
import { ThemeProvider } from '../src/lib/preferences/theme-provider.client';
import { UiProvider } from '../src/lib/preferences/ui-provider.client';

const preview: Preview = {
  parameters: {
    nextjs: {
      appDirectory: true,
      navigation: {
        pathname: '/app',
      },
    },
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    a11y: {
      test: 'todo',
    },
    backgrounds: {
      default: 'canvas',
      values: [
        { name: 'canvas', value: '#ECF0F1' },
        { name: 'white', value: '#ffffff' },
        { name: 'dark', value: '#2C3E50' },
      ],
    },
  },
  globalTypes: {
    theme: {
      description: 'Color theme for components',
      defaultValue: 'light',
      toolbar: {
        title: 'Theme',
        icon: 'circlehollow',
        items: [
          { value: 'light', title: 'Light', icon: 'sun' },
          { value: 'dark', title: 'Dark', icon: 'moon' },
        ],
        dynamicTitle: true,
      },
    },
  },
  decorators: [
    (Story, context) => {
      const theme = context.globals.theme === 'dark' ? 'dark' : 'light';

      useEffect(() => {
        const root = document.documentElement;
        if (theme === 'dark') {
          root.classList.add('dark');
        } else {
          root.classList.remove('dark');
        }
      }, [theme]);

      return (
        <ThemeProvider key={theme} initialTheme={theme}><UiProvider><PreviewProvider messages={messages}>
            <div className="font-sans antialiased text-foreground min-h-full">
              <Story />
            </div>
        </PreviewProvider></UiProvider></ThemeProvider>
      );
    },
  ],
};

export default preview;