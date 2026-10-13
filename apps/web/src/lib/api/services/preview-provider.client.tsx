'use client'

import dynamic from 'next/dynamic'

export const PreviewProvider = dynamic(() => import('./preview-runtime.client').then(module => module.PreviewRuntime))
