import { NavLink, useRouteError } from 'react-router-dom'

export default function ErrorPage() {
  const error = useRouteError()
  console.error(error)

  return (
    <section id="center">
      <h1 className="accent">Something went wrong</h1>
      <p>An unexpected error occurred. Please try again.</p>
      <NavLink to="/" className="btn accent">
        Go Home
      </NavLink>
    </section>
  )
}
