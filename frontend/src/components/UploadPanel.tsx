import { useState } from 'react';
import { Upload, Button, message, Card, Typography, Alert, Space } from 'antd';
import { InboxOutlined, UploadOutlined, CheckCircleOutlined } from '@ant-design/icons';
import type { UploadFile, UploadProps } from 'antd/es/upload';
import { getUploadUrl, uploadFile } from '../api';

const { Dragger } = Upload;
const { Text, Title } = Typography;

export function UploadPanel() {
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadSuccess, setUploadSuccess] = useState(false);
  const [lastUploadedFile, setLastUploadedFile] = useState<string>('');

  const handleUpload = async () => {
    const file = fileList[0];
    if (!file || !file.originFileObj) {
      message.error('Please select a file first');
      return;
    }

    setUploading(true);
    setUploadSuccess(false);

    try {
      // Get pre-signed URL
      const filename = 'customer_list.csv';
      const { uploadUrl } = await getUploadUrl(filename);

      // Upload file using pre-signed URL
      await uploadFile(uploadUrl, file.originFileObj);

      message.success('File uploaded successfully! Outbound calls will be triggered.');
      setUploadSuccess(true);
      setLastUploadedFile(file.name);
      setFileList([]);
    } catch (error) {
      console.error('Upload failed:', error);
      message.error('Upload failed. Please try again.');
    } finally {
      setUploading(false);
    }
  };

  const uploadProps: UploadProps = {
    accept: '.csv',
    maxCount: 1,
    fileList,
    onRemove: () => {
      setFileList([]);
      setUploadSuccess(false);
    },
    beforeUpload: (file) => {
      const isCSV = file.type === 'text/csv' || file.name.endsWith('.csv');
      if (!isCSV) {
        message.error('Only CSV files are accepted');
        return false;
      }
      // Create UploadFile with originFileObj properly set
      const uploadFile: UploadFile = {
        uid: file.uid || `-${Date.now()}`,
        name: file.name,
        status: 'done',
        originFileObj: file as any,
      };
      setFileList([uploadFile]);
      setUploadSuccess(false);
      return false;
    },
  };

  return (
    <Card>
      <Title level={4}>Upload Customer List</Title>
      <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
        Upload a CSV file containing customer information to trigger outbound calls.
        The file will replace any existing customer_list.csv.
      </Text>

      <Alert
        message="CSV Format"
        description={
          <Text code>
            customer_name,phone_number,debt_amount
            <br />
            John Doe,+1234567890,1000
          </Text>
        }
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
      />

      <Dragger {...uploadProps} style={{ marginBottom: 16 }}>
        <p className="ant-upload-drag-icon">
          <InboxOutlined />
        </p>
        <p className="ant-upload-text">Click or drag CSV file to this area</p>
        <p className="ant-upload-hint">
          Only .csv files are supported. File will be uploaded as customer_list.csv
        </p>
      </Dragger>

      <Space direction="vertical" style={{ width: '100%' }}>
        <Button
          type="primary"
          icon={<UploadOutlined />}
          onClick={handleUpload}
          loading={uploading}
          disabled={fileList.length === 0}
          block
          size="large"
        >
          {uploading ? 'Uploading...' : 'Upload and Trigger Calls'}
        </Button>

        {uploadSuccess && (
          <Alert
            message="Upload Successful"
            description={`File "${lastUploadedFile}" has been uploaded. The Lambda function will process the customer list and initiate outbound calls.`}
            type="success"
            showIcon
            icon={<CheckCircleOutlined />}
          />
        )}
      </Space>
    </Card>
  );
}
