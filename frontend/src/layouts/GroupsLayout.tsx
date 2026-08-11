import { MainLayout } from "./MainLayout";
import { Outlet } from "react-router-dom";
import { GroupsDrawerContent } from "./groups/GroupsDrawerContent";
import { GroupsRightActions } from "./groups/GroupsToolbar";
import { useGroupDrawer } from "../context/GroupDrawerContext";
import { GroupSelectionProvider } from "../context/GroupSelectionContext";

export function GroupsLayout() {
  // Provider wraps MainLayout so both the list (Outlet) and the rightActions
  // it renders in the TopBar share the same selection state.
  return (
    <GroupSelectionProvider>
      <MainLayout
        rightActions={<GroupsRightActions />}
        drawerContent={<GroupsDrawerContent />}
        useDrawer={useGroupDrawer}
      >
        <Outlet />
      </MainLayout>
    </GroupSelectionProvider>
  );
}
