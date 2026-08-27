import IoC from '@/modules/ioc'
import { SERVICES, type IHomeService } from '@/types'

export async function init() {
  IoC.getOrCreateInstance<IHomeService>(SERVICES.HOME)
}
