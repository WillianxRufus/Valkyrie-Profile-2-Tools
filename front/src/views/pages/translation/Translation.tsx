import { Link } from 'react-router-dom'
import IoC from '@/modules/ioc'
import { type ITranslationService, SERVICES } from '@/types'

export default function Translation() {
  const translationService = IoC.getOrCreateInstance<ITranslationService>(
    SERVICES.TRANSLATION
  )

  const { title, intro, bullets, docs } =
    translationService.getTranslationData()

  return (
    <section className="tool-page">
      <h1>{title}</h1>
      <p className="tool-intro">{intro}</p>

      <ul className="tool-bullets">
        {bullets.map((bullet, index) => (
          <li key={index}>{bullet.text}</li>
        ))}
      </ul>

      <div className="tool-docs">
        <h2>Reference</h2>
        <ul>
          {docs.map((doc) => (
            <li key={doc.href}>
              <a
                href={doc.href}
                target="_blank"
                rel="noreferrer"
                className="link"
              >
                {doc.label}
              </a>
            </li>
          ))}
        </ul>
      </div>

      <p className="row">
        <Link to="/" className="btn accent">
          Back home
        </Link>
      </p>
    </section>
  )
}
