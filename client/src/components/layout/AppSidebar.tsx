import { NavLink } from "react-router-dom";
import {
  Activity,
  FlaskConical,
  Gauge,
  LayoutDashboard,
  LineChart,
} from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";

const navItems = [
  { to: "/", label: "Dashboard", icon: Gauge },
  { to: "/health", label: "Health", icon: Activity },
  { to: "/uat", label: "UAT Runner", icon: FlaskConical },
  { to: "/admin", label: "Admin", icon: LayoutDashboard },
  { to: "/backtest", label: "Backtest", icon: LineChart },
];

export function AppSidebar() {
  return (
    <Sidebar>
      <SidebarHeader className="px-4 py-3">
        <span className="text-lg font-bold tracking-tight">Newton</span>
        <span className="text-xs text-muted-foreground">Trading System</span>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Navigation</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map((item) => (
                <SidebarMenuItem key={item.to}>
                  <SidebarMenuButton asChild>
                    <NavLink
                      to={item.to}
                      className={({ isActive }) =>
                        isActive ? "font-semibold text-sidebar-primary" : ""
                      }
                    >
                      <item.icon className="size-4" />
                      <span>{item.label}</span>
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
}
