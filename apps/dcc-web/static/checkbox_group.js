export function allChecked(checkboxes){return checkboxes.length>0&&[...checkboxes].every(checkbox=>checkbox.checked);}
export function setAllChecked(checkboxes,checked){for(const checkbox of checkboxes)checkbox.checked=Boolean(checked);return Boolean(checked);}
