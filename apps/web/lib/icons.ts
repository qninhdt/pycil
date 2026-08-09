"use client"

/**
 * The single icon surface for the app. Every icon in the product is imported
 * from here so the family cannot drift and the weight is set in exactly one
 * place (see `IconWeightProvider`).
 *
 * This module is a client boundary on purpose. Phosphor's `IconBase` reads
 * `IconContext` via `useContext` and the package ships no "use client"
 * directive of its own, so a Server Component importing an icon directly would
 * evaluate `createContext` in the server runtime. Icons are leaf nodes, so the
 * client payload per icon is small.
 */

export { IconContext } from "@phosphor-icons/react"
export type { Icon, IconWeight, IconProps } from "@phosphor-icons/react"

export {
  // Navigation: the three destinations plus their contextual surfaces.
  HouseIcon,
  BooksIcon,
  ChartLineUpIcon,
  MagnifyingGlassIcon,
  BellIcon,
  SparkleIcon,
  GearIcon,
  SignOutIcon,
  SignInIcon,

  // Theme.
  SunIcon,
  MoonIcon,
  DesktopIcon,

  // Loading. Used by the spinner primitive, which spins it in CSS.
  CircleNotchIcon,

  // Direction and disclosure.
  CaretRightIcon,
  CaretDownIcon,
  CaretUpIcon,
  ArrowRightIcon,
  XIcon,
  PlusIcon,
  MinusIcon,
  CheckIcon,
  DotsThreeIcon,

  // Library hierarchy: folder, deck, reference.
  FolderIcon,
  CardsThreeIcon,
  LinkSimpleIcon,
  PencilSimpleIcon,
  TrashIcon,
  ArrowsOutCardinalIcon,
  GlobeIcon,
  LockIcon,

  // Study.
  PlayIcon,
  CoffeeIcon,

  // Verdict and state.
  CheckCircleIcon,
  XCircleIcon,
  WarningIcon,
  WarningCircleIcon,
  InfoIcon,
  ClockIcon,
  HourglassIcon,
  WifiSlashIcon,

  // Progress.
  TrendUpIcon,

  // Assistant.
  PaperPlaneRightIcon,
  ChatCircleIcon,
  WrenchIcon,
  ShieldCheckIcon,
} from "@phosphor-icons/react"
