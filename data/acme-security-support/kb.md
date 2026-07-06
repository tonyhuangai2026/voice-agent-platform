# ACME Security FAQ Knowledge Base

## How to Check Device Serial Number

### Method 1: Find Serial Number on the Package Label or the Device Label

Locate the serial number (SN) printed on the physical package label or the device label.

**Example label information (Network Camera):**
- Model: CAM-1047 2.8mm
- SN: F81633931
- CAN ICES-3(B)/NMB-3(B)
- IP: 12V= 0.37A 4.5W
- PoE(802.3af,36-57V)= 0.2-0.1A
- MAC Address: 08:A1:89:C9:50:FD
- Manufacturer: ACME Security Co., Ltd.
- Address: No.555 Qianmo Road, Binjiang District, Hangzhou 310052, China
- Date: 06/2021
- Verification Code: E3861

### Method 2: Find Serial Number on Device Local Menu

#### For DVR/NVR GUI 3.0:

Navigate to: **Menu > Maintenance > System Info > Device Info**

The Device Info tab displays:

| Field | Value |
|-------|-------|
| Device Name | Embedded Net DVR |

A QR code is also available to scan via device management client.

#### For DVR/NVR GUI 4.0:

Navigate to: **Maintenance > System Info > Device Information**

The Device Information page displays:

| Field | Value |
|-------|-------|
| Device Name | Network Video Recorder |

#### For IPC (via Web Browser):

Navigate to: **Configuration > System > System Settings**

The System Settings > Basic Information page displays:

| Field | Value |
|-------|-------|
| Device Name | IP CAMERA |
| Device No. | 88 |

### Method 3: Find Serial Number with Device Discovery Tool

1. Follow the link to download the latest version of Device Discovery tool on your computer.

   https://www.example.com/support/tools/

2. Use Device Discovery software to automatically search active online devices in the same subnet with the PC running the software, and then select the required device to view its serial number.

**For IPC:**

- Device Serial No.: CAM-7A46 (S/N: SNXXXXXXXX0001)

**For NVR/DVR:**

- Device Serial No.: NVR-9632 (S/N: SNXXXXXXXX0002)

## Retrieve Password via Email

**The easiest way to retrieve your password**

When you don't use your password so often, you may forget it. How to retrieve your password in a convenient and safe way? Here is a self password reset method.

### Setting Up Reserved Email

#### For Inactive Device (GUI 3.0)

1. Activate the device firstly, then click the checkbox of **Reserved Email Settings**.
2. Input the **email address** which is used for receiving verification code.

#### For Inactive Device (GUI 4.0)

1. Activate the device firstly, then click the checkbox of **Reserved Email Settings**.
2. Input the **email address** which is used for receiving verification code.

#### For Active Device (GUI 3.0)

- For active device, please go to Configuration > User, select the admin user from the list then click **Edit**.
- Then click the Setting Icon to enter the Reserved Email Settings interface, to input the email address, which is used for receiving verification code.

#### For Active Device (GUI 4.0)

- For active device, please go to Configuration > User, select the admin user from the list then click **Modify**.
- Click the Modify Icon to input the email address which is used for receiving verification code, then click OK button.

### Forgot your password?

**Simple steps to reset your password**

#### Step 1

1. Click **Forgot Password**
2. Select **Verify by Reserved Email**
3. You'll find a QR code displayed on screen

#### Step 2

**Scan QR code using Cloud Connect**

Then your email will receive a **verification code**

- You need to use the Cloud Connect App for this function.
- If you are not registered, you can log in the Cloud Connect by "visitor mode."
- **How to scan the QR code?** Click "more" on the bottom menu, then click "Reset Device Password" to scan the QR code.

*Note: Cloud Connect V3.5.4 and above required*

#### Step 3

1. Key in the verification code
2. **Reset your password**

## How to Do Self-Service Password Reset on ACME Security Device Web GUI

When you don't use your password so often, you may forget it. How to retrieve your password in a convenient and safe way? Here is a self password reset method.

### Prerequisites: Setting Up Email for Password Reset

#### For Inactive Device
- For inactive devices, please create and reserve password to activate it, then click OK button.
- Input the email address which is used for receiving verification code and click OK button to continue.

#### For Active Device
- For active device, please go to **Configuration > User Management**, select the admin from the list and click **Modify**.
- Check **Account Security Settings**
- Input the email address which is used for receiving verification code.

### Forgot Your Password?

Simple steps to reset your password

#### Step 1

1. Click **Forgot Password**
2. Select **Verify by Reserved Email**
3. You'll find a QR code displayed on screen

#### Step 2

**Scan QR code using Cloud Connect**

Then your email will receive a verification code.

- You need to use the Cloud Connect App for this function.
- If you are not registered, you can log in the Cloud Connect by "visitor mode".
- **How to scan the QR code?** Click "more" on the bottom menu, then click "Reset Device Password" to scan the QR code.

*Requires Cloud Connect V3.5.4 and above*

#### Step 3

1. Key in the verification code (xxxxxxxx)
2. Click **Reset your password**

## How to Enable Cloud Connect Service in Device

**Version:** v1.0
**Date:** 1/3/2017
**Product:** Cameras, NVRs, DVRs

### How to Enable Cloud Connect Service in Device

Cloud Connect function can be enabled via Device Discovery tool, device local GUI (for DVRs/NVRs), device web GUI, device management client-4500 app and device management client-4200 client software.

#### Notes:
1. The Cloud Connect function is **DISABLED** by default in device.
2. For Device Discovery, device management client-4500 & device management client-4200, please wait the new version which will be released to support Cloud Connect later, we will update the contents in this document accordingly.

### Method 1: Enable Cloud Connect via Device Web Browser

**Steps:**

1. Login the device via web browser;
2. Go to **Configuration > Network > Platform Access** and enable Cloud Connect service by placing a check in the Enable checkbox.

   *Screenshot shows the web interface with:*
   - Left menu: Local, System, Network (with Basic Settings and Advanced Settings sub-items), Video/Audio, Image, Event, Storage
   - Top tabs: FTP, Email, **Platform Access**, HTTPS, QoS, 802.1x
   - Settings displayed:
     - Enable: ☑ (checked)
     - Platform Access Mode: Cloud Connect
     - Server IP: dev.eu.cloud-connect.example.com (with Custom checkbox)
     - Register Status: Online
     - Verification Code: •••••••
   - Note below: "6 to 12 letters or numbers, case sensitive. You are recommended to use a combination of no less than 8 letters or numbers."
   - Save button at bottom

3. For the first time to use, users need to create a verification code.
   1. Enter a new verification code and confirm;
   2. Read the terms of service;
   3. Click **'OK'** to save the settings.

   *Screenshot shows a "Note" dialog box with:*
   - Message: "To enable Cloud Connect service, you need to create a verification code or edit the default verification code."
   - Verification Code field (6 to 12 letters or numbers, case sensitive. You are recommended to use a combination of no less than 8 letters or numbers.)
   - Confirm Verification Code field
   - Message: "The Cloud Connect service will require internet access. Please read the 'Terms of Service' before enabling the service."
   - OK and Cancel buttons

4. Click **'Save'** after all settings.

**Note:** Users can check or modify the verification code in this page as well.

### Method 2: Enable Cloud Connect via Device Local GUI (for DVRs/NVRs)

**Steps:**

1. Enter the device local GUI, go to **Configuration > Network > Platform Access**.
2. Enable the Cloud Connect service by placing a check in the Enable checkbox.

   *Screenshot shows the local GUI with:*
   - Left menu: General, Network (highlighted), Alarm, Live View, Exceptions, User
   - Top tabs: General, **Platform Access**, PPPOE, DDNS, NTP, Email, NAT, More Settings
   - Settings displayed:
     - Enable: ☑ (checked)
     - Access Type: Cloud Connect
     - Server Address: dev.cloud-connect.example.com (with Custom checkbox: ■)
     - Enable Stream Encryption: ■ (unchecked)
     - Verification Code: LYSXPR
     - Status: Offline
   - QR code displayed below the settings
   - An inset showing the "Enable" checkbox being checked
   - Apply and Back buttons at bottom

3. For the first time to use, users need to create a verification code.
   1. Enter a new verification code;
   2. Read the terms of service and check the check box of terms of service;
   3. Click **'OK'** to save the settings.

   *Screenshot shows "Terms of Service" dialog with:*
   - Verification Code field (with text cursor)
   - Message: "To enable Cloud Connect service, you need to create a verification code or edit the default verification code."
   - Checkbox: ☑ "The Cloud Connect service will require internet access. Please read the 'Terms of Service' and the 'Privacy Statement' before enabling the service."
   - Message: "Please read the 'Terms of Service' and the 'Privacy Statement' scan the qr code"
   - QR code displayed
   - OK and Cancel buttons

4. Click **'Apply'** after all settings.

**Note:** User can check or modify the verification code in this page as well.

## How to Reset Password on Device Discovery

### Procedure

1. Open Device Discovery Tool to search online devices.
2. Select the device and click **Forget Password**.

*The Device Discovery interface shows a list of online devices with columns: ID, Device Type, Security, IPv4 Address, Port, Software Version, IPv4 Gateway, HTTP Port, Device Serial No. On the right panel, "Modify Network Parameters" section displays device details including IP Address, Port, Subnet Mask, Gateway, IPv6 Address, IPv6 Gateway, IPv6 Prefix Length, HTTP Port, Admin Password field, and buttons for "Modify" and "Forget Password".*

### Identifying the Pop-up Type

You might see one of three pop-ups after clicking "Forget Password":

**1.** If the pop-up requires a **security code**, please turn to **Method 1**.
- Pop-up shows "Restore Default Password" with a "Security Code:" input field and Confirm/Cancel buttons.

**2.** If the pop-up requires an **encrypted file**, please turn to **Method 2**.
- Pop-up shows "Reset Password" with:
  - Step 1: Click Export to download the key request file (XML file) or take a photo of the QR code. Send the XML file or QR code photo to our technical engineers. (Export button)
  - Step 2: Input the key or import the key file received from the technical engineer to reset the password for the device. 

**3.** If the pop-up requires an **encrypted file or key**, please turn to **Method 2 or 3**.
- Pop-up shows "Reset Password" with:
  - Step 1: Click Export to download the key request file (XML file) or take a photo of the QR code. Send the XML file or QR code photo to our technical engineers. (Export button, QR code displayed)
  - Step 2: Input the key or import the key file received from the technical engineer to reset the password for the device. 

### Method 1, Device Information

1. Copy **Start Time** and **Device Serial No.**, then send the information to ACME Security technical support team. The support team would send back security codes.

   *Device Discovery interface shows devices listed with "Start Time" column highlighted (e.g., 2015-12-02 15:52:15). The right panel shows "Device Serial No." highlighted.*

   **Note:** Please reboot the device to check the **Start Time**.

2. After receiving security codes, please choose one code according to **device's current time**.

   *Example security codes:*
   ```
   2015-11-27:RRrezeSezz
   2015-11-28:RzzSRrRyzd
   2015-11-29:zQeqz9yee
   2015-11-30:qQRzed9ezR
   2015-12-01:qe9ryzRQdy
   ```

3. Input security code in the "Security Code" field, then click **Confirm**.

   *"Restore Default Password" dialog shows Security Code field filled with "SeyqqeSS9R" and Confirm/Cancel buttons.*

### Method 2, XML File

1. Click **Export button** to save the XML file, then send the XML file to ACME Security technical support team.

   *"Reset Password" dialog - Step 1: Click Export to download the key request file (XML file) or take a photo of the QR code. Send the XML file or QR code photo to our technical engineers. (Export button shown)*

2. ACME Security technical support team will send the encrypted file back. Choose the path of the encrypted file (Import File), input your new password and confirm.

3. Click **Confirm** to reset password.

   *"Reset Password" dialog - Step 2 shows: Import File selected, file path "C:/Users/user@example.com/De", New Password field filled (password strength shown as "Strong"), Confirm Password field filled, Confirm/Cancel buttons.*

**Note:** The encrypted file would be valid for 48 hours.

### Method 3, QR CODE

With this method you can export the XML file or take a screenshot of QR code.

- If you export the XML file, please refer to Method 2 to reset password.
- You can also send the screenshot of QR code to ACME Security technical support team.

*QR code image displayed in the Reset Password dialog.*

1. ACME Security technical support team will send back the key consisting of numbers and letters (8 bytes).

2. Input the key (select "Input Key" radio button), type in the new password and confirm.

3. Click **Confirm** to reset password.

   *"Reset Password" dialog - Step 2 shows: "Input Key" selected, key field filled with "5b449116", New Password field (strength "Strong"), Confirm Password field, "Reset Network Cameras' Passwords" checkbox (checked), Confirm/Cancel buttons.*

**Note:** If you want to reset the password of NVR and connected cameras simultaneously, please choose "Reset Network Cameras' Passwords" option.

## How to Unbind Device from Cloud Connect Account

One device can be added only by one Cloud Connect account, if the device was added by other account, you cannot add it again. You can follow steps below to unbind your device or check the video which can help you.

### How to Unbind Device via Cloud Connect APP

- Video link: https://youtu.be/g2CpCUtDMsw

### How to unbind device via Device Discovery tool

- Video link: https://youtu.be/xzQpDkKubNg

### Steps

1. Open Cloud Connect app, tap the ADD icon.
2. Add device by scanning device QR code which is on the label of the device or input device serial number manually.
3. The app would pop up the message and unbind button. Press the unbind button to continue.
4. Input the password of ACME device.
5. Tap finish to unbind device.

## How to Add IPC with POE Function to NVR

### How to Add POE Cameras to NVR Using Manual Mode

**Steps:**

1. Connect your camera to the POE port of the switch. Connect your NVR to the same switch.

2. Go to **Camera Management -> Camera -> IP Camera**, select any channel and click **Edit**.
   - The Camera Management screen shows tabs: IP Camera, IP Camera Import/Export, PoE Information
   - Checkbox: "IP channel password is visible"
   - Columns displayed: Camera No., Add/Delete, Status, Security, IP Camera Address, Edit, Upgrade, Camera Name, Protocol
   - Channels D1 through D9 are listed with various IP addresses (e.g., 10.9.19.23, 10.9.6.12, 10.9.19.6, 192.168.254.2, 10.9.19.7, 10.9.6.2, 10.9.19.3, 192.168.254.9, 192.168.254.10)
   - Security statuses shown include "Risk Password", "Weak Password", and "N/A"
   - Buttons at bottom: Refresh, One-touch Activ..., Upgrade, Delete, One-touch Adding, Custom Adding

3. Select **Manual**, type in the **IP Camera Address** & **User Name** & **Admin Password**, click **OK**.
   - Edit IP Camera dialog shows:
     - IP Camera No.: D1
     - Adding Method: **Manual**
     - IP Camera Address: **10.9.19.234**
     - Protocol: ACME
     - Management Port: 8000
     - Channel Port: 1
     - Transfer Protocol: Auto
     - User Name: **admin**
     - Admin Password: **\*\*\*\*\*\*\*\***
   - Buttons: Protocol, OK, Cancel

4. After clicking OK, the camera is added successfully. The Camera Management screen now shows D1 with:
   - Security: Weak Password
   - IP Camera Address: 10.9.19.234
   - Camera Name: CAM-2422
   - Protocol: GENERIC

**Note:**

1. If you select the Manual mode to add the IPC with POE function, the password of the IPC could be different from NVR.
2. Do not press **One-touch Adding** unless the cameras' passwords are the same with the NVR password or the password of the camera is 12345.

### How to Add IPC with POE Function to NVR Using Plug-and-Play Mode

**Steps:**

1. Connect your camera to the POE port of the NVR. Assume you connect your camera to the POE port 2.

2. Go to **Camera Management -> Camera -> IP Camera**, highlight the second channel (D2) and click **Edit**.
   - The Camera Management screen shows D1 already connected (CAM-2422 at 10.9.19.234)
   - D2 shows IP address 10.9.6.12 with "Risk Password" security status
   - Net Receive Idle Bandwidth: 149Mbps

3. Select **Adding Method** as **Plug-and-Play**, click **OK**.
   - Edit IP Camera dialog shows:
     - IP Camera No.: D2
     - Adding Method: dropdown showing options **Manual** and **Plug-and-Play**
     - IP Camera Address: (greyed out when Plug-and-Play selected)
     - Protocol: (greyed out)
     - Management Port: (greyed out)
     - Channel Port: 1
     - Transfer Protocol: Auto
     - User Name: admin
     - Admin Password: (field available)
   - Buttons: Protocol, OK, Cancel

4. After clicking OK, the camera is added successfully. The Camera Management screen shows D2 with:
   - IP Camera Address: 192.168.254.5
   - Camera Name: FISHEYE
   - Protocol: GENERIC
   - Status: Connected (blue icon)
   - Upgrade available (green arrow icon)

**Note:**

1. Make sure your IPC camera has the same password with your NVR.
2. Do not press **One-touch Adding**.

## How to Reset Password Using the GUID File on Local GUI or by Answering Validation Questions

### Method 1: GUID File

##### Step 1: Export the GUID File (Local GUI)

1. Navigate to **Configuration > User Management**
2. Select the admin user and click **Edit User**
3. Enter the **Old Password**
4. Check **Change Password** if needed
5. Optionally enable **Enable Unlock Pattern** and **Draw Unlock Pattern**
6. Click **Export GUID** button
7. Note the **User's MAC Address** field (displayed as `00 :00 :00 :00 :00 :00`)

> **Password requirement:** Valid password range [8-16]. You can use a combination of numbers, lowercase, uppercase and special character for your password with at least two kinds of them contained.

#### Step 1: Export the GUID File (Web Client)

1. Navigate to **Configuration > User Management**
2. Click the **Export GUID File** tab
3. The User List shows: No. 1, User Name: admin, Level: Administrator

#### Step 2: Reset Password Using GUID File

1. When you forget your device password, enter the new password resetting interface by clicking **Forget password** on the login screen

2. Find the exported GUID file on the USB flash drive, then import it to reset device password

   - *GHO (Folder, 06-13-2016 17:00:36)*
   - *GUID_539451575_20161... (128B File, 10-24-2016 11:00:00) — highlighted with red box*
   - *ch18_20160624190209.txt (27.23KB File, 06-24-2016 19:29:38)*
   - *cn_windows_server_200... (3118.84MB File, 05-23-2016 16:43:02)*
   - *hi_tcpdump (837.31KB File, 09-21-2015 18:30:22)*
   - *IpcCfg_20160728164431... (22.00KB File, 07-28-2016 16:44:30)*
   - *tcpdump_l (807.17KB File, 01-21-2016 11:38:34)*
   - *Free Space: 4326.20MB*
   - *Buttons: New Folder, Import, Back*

3. Select the GUID file and click **Import**

### Method 2: Validation Question

#### Step 1: Set Security Questions

1. Navigate to **Configuration > User Management**
2. Click the **Security Question** tab
3. Configure three security questions and answers:
   - Security Question 1: (e.g., "You father's name.") + Answer
   - Security Question 2: (e.g., "You mother's name.") + Answer
   - Security Question 3: (e.g., "Your senior class teacher's name.") + Answer
4. Click **OK** to save

#### Step 2: Reset Password Using Security Questions

1. When you forget your device password, enter the new password resetting interface by clicking **Forget password** on the login screen

2. Answer all the pre-set security questions correctly

   - *Step 1: Verify Identification (current step)*
   - *Step 2: Set New Password*
   - *Step 3: Complete*

   *Fields displayed:*
   - *Verification Mode: "Security Question Verification" (dropdown)*
   - *Security Question 1: "You father's name." + Answer field*
   - *Security Question 2: "You mother's name." + Answer field*
   - *Security Question 3: "Your senior class teacher's name." + Answer field*
   - *Buttons: Next, Clear*

3. After answering all the questions correctly, you'd be able to change your device password.

## How to Solve Cloud Connect Offline Issue

| Field | Details |
|-------|---------|
| **Title** | How to Solve Cloud Connect Offline Issue |
| **Product** | Cameras, NVR, DVR |
| **Version** | V2.0 |
| **Date** | 7/12/2019 |
| **Pages** | 6 |

### Step 1: Check the Register Status

Go to device to see the register status. The status can be seen on web GUI, local GUI.

#### a) If the Enable box hasn't been checked, enable it and see the register status.

**On Camera/IP Device (Web GUI):**

Path: Configuration → Network → Advanced Settings → Platform Access tab

- **Enable:** Check the box to enable
- **Platform Access Mode:** Cloud Connect
- **Server IP:** dev.cloud-connect.example.com (Custom checkbox available)
- **Register Status:** Offline
- **Verification Code:** 6 to 12 letters (a to z, A to Z) or numbers (0 to 9), case sensitive. You are recommended to use a combination of no less than 8 letters or numbers.

**On NVR 3.0 (Local GUI):**

Path: Menu-Configuration-Network-Platform Access

- **Enable:** Checked
- **Access Type:** Cloud Connect
- **Server Address:** dev.cloud-connect.example.com (Custom checkbox available)
- **Enable Stream Encryption:** Available
- **Verification Code:** Displayed (masked)
- **Status:** Offline

**On NVR 4.0 (Local GUI):**

Path: Menu-System-Network-Advanced

Navigate to: SNMP > Email > **Platform Access** > More Settings

- **Access Type:** Cloud Connect
- **Enable:** Checked
- **Server Address:** litedev.cloud-connect.example.com (Custom checkbox available)
- **Enable Stream Encrypt...:** Checked
- **Verification Code/Encr...:** (e.g., sqq12345)
- **Status:** Online
- **Cloud Connect Account Status:** Unlinked (with Unbind button)
- QR codes available to scan via the Cloud Connect app to add the device or download the smartphone app.

#### b) If it has been enabled and the Register Status keeps offline, go to step 2.

### Step 2: Verify Network Connectivity

Make sure the device has been connected to the Internet and it can connect to the Cloud Connect Server.

#### a) Check IP Parameters

Go to device to see whether the IP parameters belong to LAN. The IP address, subnet mask and default gateway need to be set correctly.

**On Camera/IP Device (Web GUI):**

Path: Configuration → Network → Basic Settings → TCP/IP

- **NIC Type:** Auto
- **DHCP:** Unchecked
- **IPv4 Address:** 192.168.1.121 (Test button available)
- **IPv4 Subnet Mask:** 255.255.255.0
- **IPv4 Default Gateway:** 192.168.1.1
- **IPv6 Mode:** Route Advertisement 
- **Mac Address:** a4.14.37.46.84.1b
- **MTU:** 1500
- **Multicast Address:** (blank)
- **Enable Multicast Discovery:** Checked
- **DNS Server:**
  - Preferred DNS Server: 8.8.8.8
  - Alternate DNS Server: (blank)

**On NVR 3.0 (Local GUI):**

Path: Menu-Configuration-Network-General

- **NIC Type:** 10M/100M/1000M Self-adaptive
- **Enable DHCP:** Unchecked
- **IPv4 Address:** 10.5.2.25
- **IPv4 Subnet Mask:** 255.255.255.0
- **IPv4 Default Gateway:** 10.5.2.254
- **MAC Address:** bc:ad:28:ac:ed:09
- **MTU(Bytes):** 1500
- **Enable DNS DHCP:** Unchecked
- **Preferred DNS Server:** 8.8.8.8
- **Alternate DNS Server:** 114.114.114.114
- **IPv6 Address 1:** fe80::bead:28ff:feac:0
- **IPv6 Address 2:** (blank)
- **IPv6 Default Gateway:** (blank)

**On NVR 4.0 (Local GUI):**

Path: Menu-System-Network-TCP/IP

- **Working Mode:** Net Fault-Tolerance
- **Select NIC:** bond0
- **NIC Type:** 10M/100M/1000M Self-adapt
- **Enable DHCP:** Checked
- **Enable Obtain DNS...:** Unchecked
- **Preferred DNS Ser...:** 8.8.8.8
- **Alternate DNS Server:** 114.114.114.114
- **MAC Address:** 28:57:be:a0:de:ac
- **MTU(Bytes):** 1500
- **Main NIC:** LAN1

#### b) DNS Server Configuration

The DNS Server address is suggested to set as 8.8.8.8 or local frequently-used DNS address.

#### c) Change Server Address

Try to change Server address:
- Change `dev.cloud-connect.example.com` to `litedev.cloud-connect.example.com`
- Or change `litedev.cloud-connect.example.com` to `dev.cloud-connect.example.com`

#### d) Upgrade Firmware

Upgrade device to latest firmware.

### Step 3: Check the Network (If Register Status is Still Offline)

#### a) Check the Cloud Connect Server Accessible or Not

1. Connect your PC to the same LAN of the device.
2. Go to Windows start menu, input `cmd` and click Enter key.
3. Input command `ping dev.cloud-connect.example.com` and click Enter.
   - If there is response, it means the DNS server address is correct and the Cloud Connect Server IP address is returned to the device.
   - If there is no response, the DNS server address needs to be modified correctly.

   *Example successful ping result:*
   ```
   Pinging lbs-86005f718.ap-southeast-1.elb.amazonaws.com (52.77.151.68) with 32 bytes of data:
   Reply from 52.77.151.68: bytes=32 time=240ms TTL=235
   Reply from 52.77.151.68: bytes=32 time=233ms TTL=235
   Reply from 52.77.151.68: bytes=32 time=243ms TTL=235
   Reply from 52.77.151.68: bytes=32 time=238ms TTL=235

   Ping statistics for 52.77.151.68:
       Packets: Sent = 4, Received = 4, Lost = 0 (0% loss),
   Approximate round trip times in milli-seconds:
       Minimum = 233ms, Maximum = 243ms, Average = 238ms
   ```

#### b) Check if Firewall Blocks the Connection Between Device and Cloud Connect Server

1. Connect your PC to the same LAN of the device.
2. Go to Windows start menu, input `cmd` and click Enter key.
3. Input command **`telnet dev.cloud-connect.example.com 8555`** or **`telnet litedev.cloud-connect.example.com 8666`** and click Enter.
4. When the telnet works, it will display a blank terminal window (title bar shows "Telnet dev.cloud-connect.example.com").
5. If the telnet failed, you may need to check if there are settings on fire wall block the connection between the device and Cloud Connect server.