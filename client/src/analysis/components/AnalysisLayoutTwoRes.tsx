import * as React from "react";
import { Grid, Header, Icon, Segment } from "semantic-ui-react";

interface AnalysisLayoutTwoResProps {
    title: string,
    subtitle: React.ReactNode,
    left: React.ReactNode,
    mid: React.ReactNode,
    right: React.ReactNode,
    clustparams: React.ReactNode,
    toolbar?: React.ReactNode,
    title1: string, 
    title2: React.ReactNode,
    title3:string,

}

type MergedProps = AnalysisLayoutTwoResProps;

const AnalysisLayoutTwoRes: React.SFC<MergedProps> = ({
    title, subtitle,
    left, mid, right,
    toolbar, clustparams, title1, title2, title3
}) => {
// tslint:disable-next-line: no-console
    

    // handleChange({target: {checked: true}})


    

    return (
        <>
            <Header as='h3' attached="top">
                <Icon name="cog" />
                <Header.Content>{title}</Header.Content>
            </Header>
            <Segment attached={true}>
                <Grid columns={3}>
                    <Grid.Row>
                        <Grid.Column width={4}>
                            <p>{title1}</p>
                        </Grid.Column> 

                        <Grid.Column width={6}>
                            <p>{title2}</p>   

                        </Grid.Column>

                        <Grid.Column width={6}>
                            <p>{title3}</p>
                        </Grid.Column>    
                    </Grid.Row>

                    <Grid.Row>
                        <Grid.Column width={4}>
                            {left}
                        </Grid.Column>

                        <Grid.Column width={6}>
                            {mid}
                        </Grid.Column>

                        <Grid.Column width={6}>
                            {right}
                        </Grid.Column>

                    </Grid.Row>

                    <Grid.Row>
                        <Grid.Column width={10}>

                            <p>{clustparams}</p>
                            <p>{subtitle}</p>
                        </Grid.Column>

                        <Grid.Column width={6}>

                        </Grid.Column>

                    </Grid.Row>
                </Grid>
                
            </Segment>
            
            {toolbar}
        </>
    )
}

export default AnalysisLayoutTwoRes