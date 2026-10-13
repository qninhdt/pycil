import { clerkMiddleware } from '@clerk/nextjs/server'
import { NextResponse, type NextRequest, type NextFetchEvent } from 'next/server'

const isMock = process.env.NEXT_PUBLIC_DATA_MODE === 'mock'
const publishableKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY

const clerkHandler = clerkMiddleware({ signInUrl: '/login', signUpUrl: '/signup' })

export default async function proxy(request: NextRequest, event: NextFetchEvent) {
  if (isMock || !publishableKey) {
    return NextResponse.next()
  }

  // Next.js RSC requests without a session should not trigger Clerk FAPI handshake redirects (which fail CORS on WebKit)
  const isRsc = request.nextUrl.searchParams.has('_rsc') || request.headers.get('rsc') === '1'
  if (isRsc) {
    const hasSession = request.cookies.has('__session') || request.cookies.has('__client_uat')
    if (!hasSession) {
      return NextResponse.next()
    }
  }

  const response = await (clerkHandler as any)(request, event)

  // On localhost, sanitize Set-Cookie to strip Domain=localhost and convert SameSite=None to Lax
  // so WebKit does not drop them under RFC 6265 host-only rules
  if (response && (request.nextUrl.hostname === 'localhost' || !request.nextUrl.hostname.includes('.'))) {
    if (typeof response.headers?.getSetCookie === 'function') {
      const setCookies = response.headers.getSetCookie()
      if (setCookies && setCookies.length > 0) {
        const sanitized = setCookies.map((c: string) =>
          c.replace(/;\s*Domain=\.?localhost/gi, '').replace(/;\s*SameSite=None/gi, '; SameSite=Lax')
        )
        response.headers.delete('set-cookie')
        for (const c of sanitized) {
          response.headers.append('set-cookie', c)
        }
      }
    }
  }

  return response
}

export const config = {
  matcher: [
    // Skip Next.js internals and all static files, unless found in search params
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    // Always run for API routes
    '/(api|trpc)(.*)',
  ],
}
