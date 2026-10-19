-- Typeless 2.2.0: the status surface is an overlay, not a workspace tile.
o.window({ class = "^Typeless$", title = "^Status$" }, {
  tag = "-default-opacity",
  float = true,
  pin = true,
  no_focus = true,
  no_initial_focus = true,
  no_follow_mouse = true,
  border_size = 0,
  no_shadow = true,
  no_blur = true,
  opacity = "1 1",
})
