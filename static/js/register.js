//Problem: Hints are shown even when form is valid
//Solution: Hide and show them at appropriate times
var $password = $("#password");
var $confirmPassword = $("#confirm_password");

var $email = $("#Email");
var $fname = $("#fname");
var $lname = $("#lname");

//Hide hints
$("form span").hide();

function isPasswordValid() {
  var valid = $password.val().length > 4;
  if (!valid) {
      $password.next().show();
  }
  else {
      $password.next().hide();
  }
  return valid;
}

function arePasswordsMatching() {
  var match = $password.val() === $confirmPassword.val();
  if (!match) {
      $confirmPassword.next().show();
  }
  else {
      $confirmPassword.next().hide();
  }
  return match;
}

function isFilled(field) {
    var filled = field.val().length > 0;

    if (!filled) {
        field.next().show();
    }
    else {
        field.next().hide();
    }
    return filled;
}

function canSubmit() {
    isFilled($email);
    isFilled($fname);
    isFilled($lname);
    isPasswordValid();
    arePasswordsMatching();
    return (isFilled($email) && isFilled($fname) && isFilled($lname) && isPasswordValid() && arePasswordsMatching());
}

$email.focus().keyup(function() {isFilled($email);});
$fname.focus().keyup(function() {isFilled($fname);});
$lname.focus().keyup(function() {isFilled($lname);});

$password.focus().keyup(isPasswordValid);
$confirmPassword.focus().keyup(arePasswordsMatching);


/*
$("#submit").disable();



function isFilled(field) {
    var filled = field.val().length > 0
    if(filled) {
      //Hide hint if valid
      field.next().hide();
    } else {
      //else show hint
      field.next().show();
    }
    return filled;

}

function canSubmit() {
  return isPasswordValid() && arePasswordsMatching() && areFilledRequiredFields();
}

function passwordEvent(){
    //Find out if password is valid  
    if(isPasswordValid()) {
      //Hide hint if valid
      $password.next().hide();
    } else {
      //else show hint
      $password.next().show();
    }
}

function areFilledRequiredFields(){
    return isFilled($email) && isFilled($fname) && isFilled($lname);
}

function confirmPasswordEvent() {
  //Find out if password and confirmation match
  if(arePasswordsMatching()) {
    //Hide hint if match
    $confirmPassword.next().hide();
  } else {
    //else show hint 
    $confirmPassword.next().show();
  }
}

function enableSubmitEvent() {
  $("#submit").prop("disabled", !canSubmit());

  if ($("#submit").disabled) {
      $("form span").show();
  }
  else {
      $("form span").hide();
  }
}



//When event happens on password input
$password.focus(passwordEvent).keyup(passwordEvent).keyup(confirmPasswordEvent).keyup(enableSubmitEvent);

//When event happens on confirmation input
$confirmPassword.focus(confirmPasswordEvent).keyup(confirmPasswordEvent).keyup(enableSubmitEvent);

$fname.focus(areFilledRequiredFields).keyup(areFilledRequiredFields).keyup(enableSubmitEvent);
$lname.focus(areFilledRequiredFields).keyup(areFilledRequiredFields).keyup(enableSubmitEvent);
$email.focus(areFilledRequiredFields).keyup(areFilledRequiredFields).keyup(enableSubmitEvent);

$("#submit").keydown(enableSubmitEvent)

enableSubmitEvent();*/

