-- The vendor uses a transparent Status canvas for its recording HUD.
-- Do not decorate or focus that canvas as an ordinary application window.
o.window({ class = "^Typeless$", title = "^Status$" }, {
  tag = "-default-opacity",
  float = true,
  pin = true,
  border_size = 0,
  no_shadow = true,
  no_blur = true,
  opacity = "1 1",
  no_focus = true,
  no_initial_focus = true,
})
