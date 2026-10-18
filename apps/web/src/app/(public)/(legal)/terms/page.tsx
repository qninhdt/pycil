import Link from 'next/link'

export const metadata = { title: 'Terms of Service' }

export default function TermsPage() {
  return <article lang="en">
    <h1>Terms of Service</h1>
    <p>Effective October 18, 2026</p>
    <p>These terms govern your use of Pycil at pycil.qninhdt.com. Pycil helps you organize vocabulary, create study material, practice and review. By using the service, you agree to these terms. For questions, contact <a href="mailto:qndt123@gmail.com">qndt123@gmail.com</a>.</p>

    <h2>Your account</h2>
    <p>You are responsible for protecting your sign-in methods and for activity you authorize through your account. Provide accurate account information, do not impersonate others and tell us if you suspect unauthorized access. You must be legally able to agree to these terms, or have the authorization required from a parent or guardian.</p>

    <h2>Your content and publication</h2>
    <p>You retain the rights you hold in content you submit. You give Pycil permission to store, process, display and transmit that content as needed to provide the features you request, including processing by AI providers when you use an AI feature.</p>
    <p>Only submit material you have the right to use. Publishing a profile or learning material makes the selected information accessible to others. Do not publish private information about another person without authorization. Other people may keep copies of material they have already accessed.</p>

    <h2>Acceptable use</h2>
    <ul>
      <li>Do not use Pycil for unlawful activity, harassment, impersonation or infringement of another person’s rights.</li>
      <li>Do not attempt to access another user’s private information, bypass security or service limits, or disrupt the service.</li>
      <li>Do not submit malicious code, abuse automation or use the service to distribute spam.</li>
    </ul>

    <h2>AI and learning material</h2>
    <p>AI-generated definitions, questions, answers and explanations can be inaccurate, incomplete or inappropriate. Review generated material before relying on it or sharing it. Pycil is a learning aid and does not guarantee learning outcomes or the accuracy or uniqueness of generated content.</p>

    <h2>Availability and limits</h2>
    <p>Features and usage limits may change. Maintenance, provider failures or security incidents can interrupt the service. We may restrict or suspend activity that violates these terms or threatens the service, and may remove unlawful or infringing material. We do not guarantee uninterrupted availability.</p>

    <h2>Privacy and leaving the service</h2>
    <p>Our <Link href="/privacy">Privacy Policy</Link> describes information processing, service providers and retention. You can stop using Pycil at any time. For account or data deletion requests, contact <a href="mailto:qndt123@gmail.com">qndt123@gmail.com</a> from your account email. We may verify ownership before acting; existing backups follow their separate retention lifecycle.</p>

    <h2>Responsibility and changes</h2>
    <p>The service is provided as available. Nothing in these terms limits rights or responsibilities that cannot be limited under applicable law. We may update these terms as the service changes and will publish the current version and effective date here. Contact us if you have questions or believe content violates your rights.</p>
  </article>
}
