import { lazy } from 'react'

const ErrorPage = lazy(() => import('./error/ErrorPage'))
const Home = lazy(() => import('./home/Home'))
const Io = lazy(() => import('./io/Io'))
const Changelog = lazy(() => import('./changelog/Changelog'))

export { ErrorPage, Home, Io, Changelog }
