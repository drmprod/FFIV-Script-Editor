# Update to pass auto_hyphenate setting to reflow_line function calls

# Assuming the starting structure of card_canvas.py, we will modify lines 421 and any other places
# where reflow_line is called during overlay reflow.

# Example changes in the file:

# Original code (just an illustration)
# reflow_line(text, other_params)

# Updated code to include auto_hyphenate
# reflow_line(text, other_params, auto_hyphenate=auto_hyphenate)

# The actual implementation would involve locating the current function's parameters,
# and ensuring auto_hyphenate is passed correctly wherever necessary.

