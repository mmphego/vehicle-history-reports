<html>
 <body>
  <head>
   <title>
     run
   </title>
  </head>

   <form method="post">

    <input type="submit" value="GO" name="GO">
   </form>
 </body>
</html>

<?php
    if(isset($_POST['GO']))
    {
        $message = shell_exec("python3 vin_scrapper.py --vin-numbers JN8AZ2NC3G9400704 --host 23.94.44.65 --port 10998");
        print_r($message);
    }
?>