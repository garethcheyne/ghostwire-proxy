import {
  LayoutDashboard,
  Globe,
  Shield,
  Key,
  Tag,
  Settings,
  Cloud,
  Users,
  BarChart3,
  ShieldAlert,
  AlertTriangle,
  Flame,
  Monitor,
  Boxes,
  Info,
  Bell,
  BookOpen,
} from 'lucide-react'
import type { NavGroup, NavItem } from '@/components/app-shell'

export const navigation: NavGroup[] = [
  {
    title: 'Overview',
    items: [
      // The Dashboard link is the parent of every page, so it's only active on itself.
      { title: 'Dashboard', href: '/dashboard', icon: LayoutDashboard, exact: true },
    ],
  },
  {
    title: 'Proxy',
    items: [
      { title: 'Hosts', href: '/dashboard/proxy-hosts', icon: Globe },
      { title: 'Certificates', href: '/dashboard/certificates', icon: Shield },
      { title: 'DNS Providers', href: '/dashboard/dns', icon: Cloud },
    ],
  },
  {
    title: 'Security',
    items: [
      { title: 'Threats', href: '/dashboard/threats', icon: AlertTriangle },
      { title: 'Rules', href: '/dashboard/rules', icon: ShieldAlert },
      { title: 'Access Control', href: '/dashboard/access-control', icon: Key },
      { title: 'Known IPs', href: '/dashboard/known-ips', icon: Tag },
      { title: 'Firewalls', href: '/dashboard/firewalls', icon: Flame },
    ],
  },
  {
    title: 'Monitoring',
    items: [
      { title: 'Analytics', href: '/dashboard/analytics', icon: BarChart3 },
      { title: 'Alerts', href: '/dashboard/alerts', icon: Bell },
      { title: 'System', href: '/dashboard/system', icon: Monitor },
      { title: 'Containers', href: '/dashboard/containers', icon: Boxes },
    ],
  },
  {
    title: 'Administration',
    items: [
      { title: 'Users', href: '/dashboard/users', icon: Users },
      { title: 'Settings', href: '/dashboard/settings', icon: Settings },
      { title: 'About', href: '/dashboard/about', icon: Info },
    ],
  },
  {
    title: 'Help',
    items: [
      { title: 'Documentation', href: '/dashboard/docs', icon: BookOpen },
    ],
  },
]

/**
 * The phone bottom bar: the four destinations worth one thumb tap. Everything else stays behind
 * "More", which opens the sidebar sheet.
 */
export const mobileTabs: NavItem[] = [
  { title: 'Home', href: '/dashboard', icon: LayoutDashboard, exact: true },
  { title: 'Hosts', href: '/dashboard/proxy-hosts', icon: Globe },
  { title: 'Threats', href: '/dashboard/threats', icon: AlertTriangle },
  { title: 'Analytics', href: '/dashboard/analytics', icon: BarChart3 },
]
