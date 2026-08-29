import { NavLink, Link } from 'react-router-dom'

const links = [
  { to: '/', label: 'Home', end: true },
  { to: '/translation', label: 'Translation' },
  { to: '/cheats', label: 'Cheats' },
  { to: '/voices', label: 'Voices' },
  { to: '/about', label: 'About' },
  { to: '/changelog', label: 'Changelog' }
]

export default function Navbar() {
  return (
    <nav className="navbar" aria-label="Primary">
      <Link to="/" className="navbar-brand">
        VP2 Tools
      </Link>
      <ul className="navbar-links">
        {links.map((link) => (
          <li key={link.to}>
            <NavLink
              to={link.to}
              end={link.end}
              className={({ isActive }) =>
                `navbar-link${isActive ? ' active' : ''}`
              }
            >
              {link.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
