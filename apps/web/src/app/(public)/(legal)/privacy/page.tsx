import Link from 'next/link'

export const metadata = { title: 'Privacy Policy' }

export default function PrivacyPage() {
  return <article lang="en">
    <h1>Privacy Policy</h1>
    <p>Effective October 18, 2026</p>
    <p>Pycil is a vocabulary learning application at pycil.qninhdt.com. This policy explains how Pycil collects, uses, shares and retains information when you browse, create an account, organize vocabulary or use its AI and study features. The operator can be contacted at <a href="mailto:qndt123@gmail.com">qndt123@gmail.com</a>.</p>

    <h2>Information we collect</h2>
    <ul>
      <li><strong>Account information:</strong> your authentication identifier, email address and available profile information, such as your name and profile image. Clerk handles authentication. If you choose Google sign-in, Google provides the basic identity information you authorize. Pycil requests identity scopes, not access to your Gmail messages, contacts, Drive or calendar.</li>
      <li><strong>Learning and profile information:</strong> your handle, bio, preferences, libraries, decks, saved vocabulary, study answers and learning progress, together with content you choose to publish.</li>
      <li><strong>AI interactions:</strong> prompts, assistant conversations, selected vocabulary and other context you provide or select when requesting generation, study preparation or assistant help.</li>
      <li><strong>Operational information:</strong> request timestamps, routes, response status, duration, request identifiers and error information used to operate and diagnose the service. Infrastructure providers may process network information, including IP addresses and browser information, when serving requests.</li>
    </ul>

    <h2>How we use information</h2>
    <p>We use this information to authenticate you, maintain your account, save and display your material, personalize study sessions, track learning progress, fulfill AI requests, enforce access controls and service limits, investigate failures and protect the service from abuse.</p>
    <p>Google identity information is used for sign-in and account identity. It is not provided to an AI model to train a general-purpose model. Do not put passwords, payment information or sensitive personal information in prompts, vocabulary notes or public material.</p>

    <h2>AI processing and service providers</h2>
    <p>When you use an AI feature, relevant prompts, conversation history, selected learning content and settings are sent through OpenRouter to the model provider selected for that feature. This processing is necessary to produce the requested response. The providers may process and retain requests under their own policies; this policy does not promise zero retention or a particular provider training setting.</p>
    <p>Clerk processes authentication and identity information. Vercel hosts the website, Cloudflare handles API traffic and security, and AWS S3 stores encrypted database backups. The application backend and database run on a VPS. These providers process information as needed to deliver their services, and processing may occur outside your country.</p>
    <p>See the policies of <a href="https://clerk.com/legal/privacy">Clerk</a>, <a href="https://openrouter.ai/privacy">OpenRouter</a>, <a href="https://vercel.com/legal/privacy-policy">Vercel</a>, <a href="https://www.cloudflare.com/privacypolicy/">Cloudflare</a> and <a href="https://aws.amazon.com/privacy/">AWS</a> for their handling of information.</p>

    <h2>Public and private material</h2>
    <p>Publishing material makes it accessible to other users and visitors. Your public profile may display your handle, bio and published libraries. Personal libraries, private preferences and individual learning progress are protected by application access controls. Public material may be viewed or copied by others; removing it from Pycil cannot remove copies others have already made.</p>

    <h2>Cookies and browser storage</h2>
    <p>Pycil and its authentication provider use cookies and browser storage for sign-in, session security and interface preferences such as language and theme. Blocking or clearing this storage can sign you out or reset preferences. Hosting and security providers may also use storage needed to protect and deliver their services.</p>

    <h2>Retention and security</h2>
    <p>Account and learning information is retained while needed to provide your account and requested features. Operational records and backups have separate retention cycles. Removing information from the active application does not immediately remove it from existing backups; those copies remain subject to their retention and recovery lifecycle.</p>
    <p>We use HTTPS, access controls and encrypted backups to protect information. No service or transmission is completely secure. We do not promise a fixed deletion deadline or retention period that the service cannot reliably enforce.</p>

    <h2>Your choices and requests</h2>
    <p>You can change supported profile and learning settings and control which material you publish. To request access, correction, a copy of your information or deletion of your account and associated information, contact <a href="mailto:qndt123@gmail.com">qndt123@gmail.com</a> from your account email. We may ask you to verify account ownership before acting. Some records may need to be retained to address security incidents or legal obligations.</p>
    <p>You can also revoke Google access through your Google Account settings. Revoking that connection stops future authorization through it; it does not by itself delete your Pycil account or existing learning records.</p>

    <h2>Changes and contact</h2>
    <p>We will update this page and its effective date when this policy changes. Questions about this policy or data handling can be sent to <a href="mailto:qndt123@gmail.com">qndt123@gmail.com</a>. See also our <Link href="/terms">Terms of Service</Link>.</p>
  </article>
}
