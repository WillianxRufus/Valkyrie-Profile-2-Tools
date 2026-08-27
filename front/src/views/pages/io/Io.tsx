import { Link } from 'react-router-dom'
import IoC from '@/modules/ioc'
import { SERVICES, type IHomeService } from '@/types'

function Io() {
  const homeService = IoC.getOrCreateInstance<IHomeService>(SERVICES.HOME)

  const count = homeService.getCount()

  return (
    <section id="center">
      <p>{count}</p>
      <div className="row">
        <button className="btn" onClick={() => homeService.increment()}>
          +
        </button>
        <button className="btn" onClick={() => homeService.decrement()}>
          -
        </button>
        <button className="btn" onClick={() => homeService.reset()}>
          reset
        </button>
      </div>
      <p>
        <Link to="/" className="btn accent">
          Back home
        </Link>
      </p>
    </section>
  )
}

export default Io
